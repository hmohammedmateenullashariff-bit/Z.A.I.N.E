"""
autonomy/scheduler.py
Scheduled and background goal runner with global quiet mode, Obsidian + Telegram
delivery, and unattended approval-pause support.

Strictly gated behind ZAINE_AGENT=1 and serialized through RequestCoordinator
so the single local 7B model on the RTX 2050 4GB GPU is never contested.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from autonomy.guards import unattended_run_scope
from autonomy.loop import AutonomousLoop, LoopConfig, LoopResult
from autonomy.scratchpad import (
    RunScratchpad,
    RunScratchpadStore,
    atomic_write_json,
    flush_run_to_vault,
    utc_now_iso,
)

VALID_SCHEDULE_KINDS = ("background", "once", "interval", "daily")
DEFAULT_STATE_VERSION = 1
_MAX_QUIET_DIGEST = 50


def _agent_enabled() -> bool:
    return os.getenv("ZAINE_AGENT", "0").strip().lower() in ("1", "true", "yes", "on")


def get_scheduler_dir() -> Path:
    """Returns the persistence directory for scheduler jobs and quiet mode state."""
    override = os.getenv("ZAINE_SCHEDULER_DIR", "").strip()
    base = Path(override) if override else (Path(__file__).resolve().parent.parent / "data" / "scheduler")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _parse_iso_utc(raw: str) -> Optional[_dt.datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = _dt.datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt.astimezone(_dt.timezone.utc)
    except ValueError:
        return None


def compute_next_daily_run(daily_time: str, *, now_local: Optional[_dt.datetime] = None) -> _dt.datetime:
    """Computes the next UTC datetime corresponding to a local 'HH:MM' daily schedule."""
    raw = str(daily_time or "").strip()
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid daily_time '{daily_time}'; expected 'HH:MM'.")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"Invalid daily_time '{daily_time}'; expected 'HH:MM'.") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Out-of-range daily_time '{daily_time}'; expected 00:00..23:59.")

    local_now = now_local if now_local is not None else _dt.datetime.now().astimezone()
    if local_now.tzinfo is None:
        local_now = local_now.astimezone()
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate = candidate + _dt.timedelta(days=1)
    return candidate.astimezone(_dt.timezone.utc)


@dataclass
class ScheduledGoal:
    """Persistent definition and runtime state of a scheduled or background autonomous goal."""

    job_id: str
    goal: str
    schedule_kind: str = "background"  # background | once | interval | daily
    interval_seconds: int = 0
    daily_time: str = ""
    run_at: str = ""
    next_run_at: str = ""
    enabled: bool = True
    status: str = "pending"  # pending | running | paused_approval | completed | failed | cancelled
    max_steps: int = 8
    last_run_at: str = ""
    last_run_id: str = ""
    last_status: str = ""
    last_summary: str = ""
    last_error: str = ""
    pending_approval_id: str = ""
    pending_tool: str = ""
    obsidian_note_id: str = ""
    telegram_notified: bool = False
    run_count: int = 0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ScheduledGoal":
        return cls(
            job_id=str(raw.get("job_id") or f"JOB-{uuid.uuid4().hex[:8].upper()}"),
            goal=str(raw.get("goal") or ""),
            schedule_kind=str(raw.get("schedule_kind") or "background"),
            interval_seconds=int(raw.get("interval_seconds") or 0),
            daily_time=str(raw.get("daily_time") or ""),
            run_at=str(raw.get("run_at") or ""),
            next_run_at=str(raw.get("next_run_at") or ""),
            enabled=bool(raw.get("enabled", True)),
            status=str(raw.get("status") or "pending"),
            max_steps=max(1, int(raw.get("max_steps") or 8)),
            last_run_at=str(raw.get("last_run_at") or ""),
            last_run_id=str(raw.get("last_run_id") or ""),
            last_status=str(raw.get("last_status") or ""),
            last_summary=str(raw.get("last_summary") or ""),
            last_error=str(raw.get("last_error") or ""),
            pending_approval_id=str(raw.get("pending_approval_id") or ""),
            pending_tool=str(raw.get("pending_tool") or ""),
            obsidian_note_id=str(raw.get("obsidian_note_id") or ""),
            telegram_notified=bool(raw.get("telegram_notified", False)),
            run_count=int(raw.get("run_count") or 0),
            created_at=str(raw.get("created_at") or utc_now_iso()),
            updated_at=str(raw.get("updated_at") or utc_now_iso()),
        )


class SchedulerStore:
    """Thread-safe atomic JSON persistence store for scheduler jobs and quiet-mode state."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._explicit_dir = Path(base_dir) if base_dir is not None else None
        self._lock = threading.RLock()

    @property
    def state_path(self) -> Path:
        root = self._explicit_dir if self._explicit_dir is not None else get_scheduler_dir()
        root.mkdir(parents=True, exist_ok=True)
        return root / "state.json"

    def _default_state(self) -> Dict[str, Any]:
        return {
            "version": DEFAULT_STATE_VERSION,
            "quiet_mode": False,
            "quiet_updated_at": "",
            "quiet_reason": "",
            "quiet_digest": [],
            "jobs": [],
        }

    def load_state(self) -> Dict[str, Any]:
        with self._lock:
            fp = self.state_path
            if not fp.exists():
                return self._default_state()
            try:
                raw = json.loads(fp.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    return self._default_state()
                base = self._default_state()
                base.update(raw)
                if not isinstance(base.get("jobs"), list):
                    base["jobs"] = []
                if not isinstance(base.get("quiet_digest"), list):
                    base["quiet_digest"] = []
                return base
            except Exception:
                return self._default_state()

    def save_state(self, state: Dict[str, Any]) -> Path:
        with self._lock:
            fp = self.state_path
            atomic_write_json(fp, state)
            return fp

    def mutate(self, fn: Callable[[Dict[str, Any]], Any]) -> Any:
        with self._lock:
            state = self.load_state()
            res = fn(state)
            self.save_state(state)
            return res


_DEFAULT_STORE = SchedulerStore()


def is_quiet_mode() -> bool:
    """Returns True when global quiet mode is active via env ZAINE_QUIET_MODE or persisted state."""
    env_val = os.getenv("ZAINE_QUIET_MODE", "").strip().lower()
    if env_val in ("1", "true", "yes", "on"):
        return True
    if env_val in ("0", "false", "no", "off"):
        # Explicit '0'/'false' does NOT override a runtime persisted toggle unless env is unset/false?
        # Keep persisted toggle authoritative unless ZAINE_QUIET_MODE=1 forces it ON.
        pass
    try:
        state = _DEFAULT_STORE.load_state()
        return bool(state.get("quiet_mode", False))
    except Exception:
        return False


def set_quiet_mode(enabled: bool, *, reason: str = "") -> Dict[str, Any]:
    """Enables or disables global quiet mode and returns updated quiet-mode status."""
    now = utc_now_iso()

    def _apply(state: Dict[str, Any]) -> None:
        state["quiet_mode"] = bool(enabled)
        state["quiet_updated_at"] = now
        state["quiet_reason"] = str(reason or "").strip()[:240]

    _DEFAULT_STORE.mutate(_apply)
    return get_quiet_status()


def record_quiet_suppression(
    *,
    channel: str,
    summary: str,
    job_id: str = "",
    proposal_id: str = "",
) -> None:
    """Appends a suppressed notification to the quiet-mode digest for later inspection."""
    entry = {
        "ts": utc_now_iso(),
        "channel": str(channel or "alert"),
        "job_id": str(job_id or ""),
        "proposal_id": str(proposal_id or ""),
        "summary": str(summary or "")[:300],
    }

    def _apply(state: Dict[str, Any]) -> None:
        digest = list(state.get("quiet_digest") or [])
        digest.append(entry)
        state["quiet_digest"] = digest[-_MAX_QUIET_DIGEST:]

    try:
        _DEFAULT_STORE.mutate(_apply)
    except Exception:
        pass


def get_quiet_status(*, clear_digest: bool = False) -> Dict[str, Any]:
    """Returns global quiet-mode status and buffered suppressed notification digest."""
    env_forced = os.getenv("ZAINE_QUIET_MODE", "").strip().lower() in ("1", "true", "yes", "on")

    def _read(state: Dict[str, Any]) -> Dict[str, Any]:
        digest = list(state.get("quiet_digest") or [])
        enabled = bool(env_forced or state.get("quiet_mode", False))
        info = {
            "enabled": enabled,
            "env_forced": env_forced,
            "persisted": bool(state.get("quiet_mode", False)),
            "updated_at": str(state.get("quiet_updated_at") or ""),
            "reason": str(state.get("quiet_reason") or ""),
            "suppressed_count": len(digest),
            "digest": digest,
        }
        if clear_digest:
            state["quiet_digest"] = []
        return info

    if clear_digest:
        return _DEFAULT_STORE.mutate(_read)
    return _read(_DEFAULT_STORE.load_state())


LoopFactory = Callable[[ScheduledGoal, str], AutonomousLoop]


class GoalScheduler:
    """
    Executes scheduled and background autonomous goals sequentially through RequestCoordinator.

    Guarantees:
    - Gated behind ZAINE_AGENT=1 (never spawns autonomous work when ZAINE_AGENT=0).
    - Serialized via RequestCoordinator + internal lock so interactive chat and scheduled jobs
      never run simultaneous GPU inference.
    - Risky tool calls pause and create persistent ApprovalRegistry PENDING proposals rather than
      auto-approving.
    - Results land in the configured Obsidian vault (PROVISIONAL trust, LOCAL_ONLY taint) and
      Telegram (unless global quiet mode is active).
    """

    def __init__(
        self,
        *,
        store: Optional[SchedulerStore] = None,
        agent: Optional[Any] = None,
        loop_factory: Optional[LoopFactory] = None,
        poll_interval_s: float = 5.0,
    ) -> None:
        self._store = store if store is not None else SchedulerStore()
        self._agent = agent
        self._loop_factory = loop_factory
        self._poll_interval_s = max(0.2, float(poll_interval_s))
        self._exec_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running_job_id: str = ""

    def bind_agent(self, agent: Any) -> None:
        """Binds or updates the active ZaineAgent instance used for scheduled runs."""
        self._agent = agent

    def set_loop_factory(self, loop_factory: Optional[LoopFactory]) -> None:
        """Overrides loop creation (primarily used by deterministic tests)."""
        self._loop_factory = loop_factory

    def _compute_initial_next_run(
        self,
        *,
        schedule_kind: str,
        interval_seconds: int,
        daily_time: str,
        run_at: str,
        now_utc: _dt.datetime,
    ) -> str:
        if schedule_kind == "background":
            return now_utc.isoformat()
        if schedule_kind == "once":
            if run_at:
                parsed = _parse_iso_utc(run_at)
                if parsed is None:
                    raise ValueError(f"Invalid run_at timestamp '{run_at}'.")
                return parsed.isoformat()
            delay = max(0, int(interval_seconds or 0))
            return (now_utc + _dt.timedelta(seconds=delay)).isoformat()
        if schedule_kind == "interval":
            secs = int(interval_seconds or 0)
            if secs < 1:
                raise ValueError("interval_seconds must be >= 1 for 'interval' schedule.")
            return (now_utc + _dt.timedelta(seconds=secs)).isoformat()
        if schedule_kind == "daily":
            next_dt = compute_next_daily_run(daily_time, now_local=now_utc.astimezone())
            return next_dt.isoformat()
        raise ValueError(f"Unsupported schedule_kind '{schedule_kind}'. Expected one of {VALID_SCHEDULE_KINDS}.")

    def add_job(
        self,
        goal: str,
        *,
        schedule_kind: str = "background",
        interval_seconds: int = 0,
        daily_time: str = "",
        run_at: str = "",
        max_steps: int = 8,
        run_immediately: Optional[bool] = None,
    ) -> ScheduledGoal:
        """Registers a persistent background or scheduled goal."""
        clean_goal = str(goal or "").strip()
        if not clean_goal:
            raise ValueError("Goal cannot be empty.")
        kind = str(schedule_kind or "background").strip().lower()
        if kind not in VALID_SCHEDULE_KINDS:
            raise ValueError(f"Invalid schedule_kind '{kind}'. Must be one of {VALID_SCHEDULE_KINDS}.")

        now_utc = _utc_now()
        if kind == "interval" and run_immediately:
            if int(interval_seconds or 0) < 1:
                raise ValueError("interval_seconds must be >= 1 for 'interval' schedule.")
            next_run = now_utc.isoformat()
        else:
            next_run = self._compute_initial_next_run(
                schedule_kind=kind,
                interval_seconds=interval_seconds,
                daily_time=daily_time,
                run_at=run_at,
                now_utc=now_utc,
            )

        job = ScheduledGoal(
            job_id=f"JOB-{uuid.uuid4().hex[:8].upper()}",
            goal=clean_goal,
            schedule_kind=kind,
            interval_seconds=max(0, int(interval_seconds or 0)),
            daily_time=str(daily_time or "").strip(),
            run_at=str(run_at or "").strip(),
            next_run_at=next_run,
            enabled=True,
            status="pending",
            max_steps=max(1, int(max_steps or 8)),
            created_at=now_utc.isoformat(),
            updated_at=now_utc.isoformat(),
        )

        def _append(state: Dict[str, Any]) -> None:
            jobs = list(state.get("jobs") or [])
            jobs.append(job.to_dict())
            state["jobs"] = jobs

        with self._state_lock:
            self._store.mutate(_append)
        return job

    def enqueue_background(self, goal: str, *, max_steps: int = 8) -> ScheduledGoal:
        """Convenience helper to enqueue a one-off background autonomous goal."""
        return self.add_job(goal, schedule_kind="background", max_steps=max_steps)

    def _find_and_update_job(self, job_id: str, updater: Callable[[ScheduledGoal], None]) -> Optional[ScheduledGoal]:
        target_id = str(job_id or "").strip().upper()
        updated_job: Optional[ScheduledGoal] = None

        def _apply(state: Dict[str, Any]) -> None:
            nonlocal updated_job
            jobs = list(state.get("jobs") or [])
            new_jobs: List[Dict[str, Any]] = []
            for raw in jobs:
                item = ScheduledGoal.from_dict(raw)
                if item.job_id.upper() == target_id:
                    updater(item)
                    item.updated_at = utc_now_iso()
                    updated_job = item
                new_jobs.append(item.to_dict())
            state["jobs"] = new_jobs

        with self._state_lock:
            self._store.mutate(_apply)
        return updated_job

    def get_job(self, job_id: str) -> Optional[ScheduledGoal]:
        target_id = str(job_id or "").strip().upper()
        state = self._store.load_state()
        for raw in state.get("jobs") or []:
            item = ScheduledGoal.from_dict(raw)
            if item.job_id.upper() == target_id:
                return item
        return None

    def cancel_job(self, job_id: str) -> Optional[ScheduledGoal]:
        """Cancels a pending, paused, or running scheduled/background job."""
        job = self.get_job(job_id)
        if job is None:
            return None

        # Signal cancellation if it happens to be actively running
        if job.last_run_id:
            try:
                from autonomy.cancel import cancel_run
                cancel_run(job.last_run_id)
            except Exception:
                pass

        def _mark_cancel(item: ScheduledGoal) -> None:
            item.enabled = False
            item.status = "cancelled"
            item.next_run_at = ""
            item.pending_approval_id = ""
            item.pending_tool = ""

        return self._find_and_update_job(job.job_id, _mark_cancel)

    def list_jobs(self, *, include_inactive: bool = True) -> List[Dict[str, Any]]:
        state = self._store.load_state()
        out: List[Dict[str, Any]] = []
        for raw in state.get("jobs") or []:
            item = ScheduledGoal.from_dict(raw)
            if not include_inactive and item.status in ("completed", "cancelled"):
                continue
            out.append(item.to_dict())
        out.sort(key=lambda j: j.get("created_at") or "", reverse=True)
        return out

    def get_status(self) -> Dict[str, Any]:
        jobs = self.list_jobs(include_inactive=True)
        active = [j for j in jobs if j.get("enabled") and j.get("status") not in ("completed", "cancelled")]
        paused = [j for j in jobs if j.get("status") == "paused_approval"]
        return {
            "enabled": _agent_enabled(),
            "worker_alive": bool(self._thread is not None and self._thread.is_alive()),
            "running_job_id": self._running_job_id,
            "total_jobs": len(jobs),
            "active_jobs": len(active),
            "paused_jobs": len(paused),
            "quiet": get_quiet_status(),
            "jobs": jobs,
        }

    def _build_loop(self, job: ScheduledGoal, request_id: str) -> AutonomousLoop:
        if self._loop_factory is not None:
            loop = self._loop_factory(job, request_id)
            if hasattr(loop, "_suppress_vault_flush"):
                loop._suppress_vault_flush = True
            return loop

        from agent import build_clustered_system_prompt, resolve_tool_alias
        from agents.registry import get_registry, select_agent
        from autonomy.memory_bridge import retrieve_step_memory
        from core_router import router
        from tools import TOOL_REGISTRY

        model_name = "zaine-reflex-7b"
        try:
            if getattr(router, "single_model", True):
                target_model = os.getenv("ZAINE_AGENT_MODEL", "zaine-reflex-7b")
            else:
                target_model = router.reflex_model or "zaine-reflex-7b"
            model_name = router.resolve_model(target_model)
        except Exception:
            pass

        task_tier = "GENERAL"
        try:
            task_tier = router.classify_task_tier(job.goal)
        except Exception:
            pass

        profile = None
        try:
            profile = select_agent(job.goal, task_tier).profile
        except Exception:
            try:
                profile = get_registry().default
            except Exception:
                profile = None

        tool_exec_fn = getattr(self._agent, "_execute_tool", None) if self._agent is not None else None
        if tool_exec_fn is None:
            def _direct_tool_exec(tc: Dict[str, Any]) -> str:
                tname = str(tc.get("tool") or "").strip()
                args = dict(tc.get("args") or {})
                fn = TOOL_REGISTRY.get(tname)
                if fn is None:
                    return f"Error: unknown tool '{tname}'"
                return str(fn(**args))
            tool_exec_fn = _direct_tool_exec

        active_clusters: List[str] = []
        if self._agent is not None and profile is not None and hasattr(self._agent, "_agent_clusters"):
            try:
                active_clusters = list(self._agent._agent_clusters(profile, job.goal))
            except Exception:
                active_clusters = []

        try:
            sys_prompt = build_clustered_system_prompt(
                "",
                ultron_mode=bool(getattr(self._agent, "ultron_mode", False)) if self._agent is not None else False,
                active_clusters=active_clusters,
                agent_profile=profile,
            )
        except Exception:
            sys_prompt = str(getattr(profile, "system_prompt", "") or "")

        mem_ctx = ""
        try:
            mem_ctx, _ = retrieve_step_memory(job.goal, max_chars=2000, mark_taint=False)
        except Exception:
            mem_ctx = ""

        res_store = None
        if self._agent is not None:
            try:
                self._agent._turn_event_cb = None
                self._agent._turn_model = model_name
                self._agent._turn_thread = threading.current_thread()
                self._agent._delegation_depth = 0
            except Exception:
                pass
            try:
                if hasattr(self._agent, "_result_store"):
                    res_store = self._agent._result_store()
            except Exception:
                res_store = None

        cfg = LoopConfig.from_env(model_name=model_name, max_steps=job.max_steps)
        return AutonomousLoop(
            config=cfg,
            profile=profile,
            tool_exec_fn=tool_exec_fn,
            tool_alias_fn=resolve_tool_alias,
            system_prompt=sys_prompt,
            memory_context=mem_ctx,
            request_id=request_id,
            result_store=res_store,
            allow_delegation=True,
            delegation_depth=0,
            suppress_vault_flush=True,
        )

    def _deliver_notifications(self, job: ScheduledGoal, result: LoopResult) -> tuple[str, bool]:
        """Flushes result to Obsidian vault and sends Telegram summary (honoring quiet mode)."""
        note_id = ""
        try:
            pad = RunScratchpadStore().load(result.run_id)
        except Exception:
            pad = None
        if pad is None:
            pad = RunScratchpad(
                run_id=result.run_id,
                task=job.goal,
                agent_id="zaine-jarvis",
                status=result.status,
                completed_steps=int(result.steps_executed or 0),
                max_steps=int(result.max_steps or job.max_steps),
                artifacts=list(result.artifacts),
                final_summary=result.summary,
                privacy_taint="LOCAL_ONLY",
            )
        if os.getenv("ZAINE_OBSIDIAN_VAULT_PATH", "").strip():
            note_id = flush_run_to_vault(
                pad,
                extra_tags=["scheduled-goal", job.schedule_kind],
                title_prefix=f"[{job.schedule_kind.capitalize()}]",
            ) or ""

        prefix = "Background" if job.schedule_kind == "background" else f"Scheduled ({job.schedule_kind})"
        status_label = result.status.upper()
        lines = [
            f"[Z.A.I.N.E {prefix}] {job.job_id} — {status_label}",
            f"Goal: {job.goal[:120]}",
            f"Steps: {result.steps_executed}/{result.max_steps}",
        ]
        if result.artifacts:
            lines.append("Artifacts: " + ", ".join(result.artifacts[:5]))
        if note_id:
            lines.append(f"Vault Note: {note_id}")
        if result.status == "paused" and result.pending_approval_id:
            lines.append(
                f"Action Required: Approval {result.pending_approval_id} pending for '{result.pending_tool}'. "
                "Approve to resume."
            )
        if result.summary:
            lines.append(result.summary[:400])
        msg_text = "\n".join(lines)

        if is_quiet_mode():
            record_quiet_suppression(
                channel="telegram_scheduler",
                summary=msg_text,
                job_id=job.job_id,
                proposal_id=result.pending_approval_id,
            )
            return note_id, False

        sent = False
        try:
            from telegram_bridge import send_telegram_alert
            sent = bool(send_telegram_alert(msg_text))
        except Exception:
            sent = False
        return note_id, sent

    def _advance_after_run(self, item: ScheduledGoal, now_utc: _dt.datetime) -> None:
        if item.schedule_kind in ("background", "once"):
            item.next_run_at = ""
            item.enabled = False
        elif item.schedule_kind == "interval":
            secs = max(1, int(item.interval_seconds or 60))
            item.next_run_at = (now_utc + _dt.timedelta(seconds=secs)).isoformat()
            item.enabled = True
        elif item.schedule_kind == "daily":
            next_dt = compute_next_daily_run(
                item.daily_time,
                now_local=(now_utc + _dt.timedelta(seconds=1)).astimezone(),
            )
            item.next_run_at = next_dt.isoformat()
            item.enabled = True

    def _execute_job(self, job: ScheduledGoal, *, resume_run_id: str = "") -> Dict[str, Any]:
        """Executes (or resumes) a single job sequentially through RequestCoordinator."""
        from approval import set_current_request_id
        from coordinator import get_request_coordinator

        with self._exec_lock:
            self._running_job_id = job.job_id
            req_id = f"sched-{job.job_id}-{uuid.uuid4().hex[:6]}"
            self._find_and_update_job(
                job.job_id,
                lambda it: setattr(it, "status", "running"),
            )
            coord = get_request_coordinator()
            wait_limit = max(30.0, float(os.getenv("ZAINE_SCHEDULER_QUEUE_TIMEOUT_S", "300") or "300"))
            claim_status, m_req, _cached = coord.claim_request(request_id=req_id, client="scheduler")

            try:
                if claim_status == "claimed" and m_req.state == "queued":
                    if not m_req.wait_for_turn(timeout=wait_limit):
                        coord.fail_request(req_id, "Timed out waiting for coordinator turn")
                        self._find_and_update_job(
                            job.job_id,
                            lambda it: (
                                setattr(it, "status", "failed"),
                                setattr(it, "last_status", "timeout_queue"),
                                setattr(it, "last_error", "Timed out waiting in RequestCoordinator queue"),
                            ),
                        )
                        return {"job_id": job.job_id, "status": "failed", "error": "coordinator_queue_timeout"}

                set_current_request_id(req_id)
                with unattended_run_scope(pause_on_approval=True):
                    loop = self._build_loop(job, req_id)
                    if resume_run_id:
                        result = loop.resume(resume_run_id)
                    else:
                        result = loop.run(job.goal)

                now_utc = _utc_now()
                note_id, tg_sent = self._deliver_notifications(job, result)

                def _apply_done(it: ScheduledGoal) -> None:
                    it.last_run_at = now_utc.isoformat()
                    it.last_run_id = result.run_id
                    it.last_status = result.status
                    it.last_summary = (result.summary or "")[:600]
                    it.last_error = "; ".join(result.errors[:3]) if result.errors else ""
                    it.obsidian_note_id = note_id or it.obsidian_note_id
                    it.telegram_notified = bool(tg_sent)
                    it.run_count = int(it.run_count or 0) + (0 if resume_run_id else 1)
                    if result.status == "paused":
                        it.status = "paused_approval"
                        it.pending_approval_id = result.pending_approval_id
                        it.pending_tool = result.pending_tool
                        # Keep interval/daily job paused without re-spawning duplicates until approved/denied
                    else:
                        it.pending_approval_id = ""
                        it.pending_tool = ""
                        if result.status == "completed":
                            it.status = "pending" if it.schedule_kind in ("interval", "daily") else "completed"
                        elif result.status == "cancelled":
                            it.status = "cancelled"
                            it.enabled = False
                            it.next_run_at = ""
                            coord.complete_request(req_id, {"run_id": result.run_id, "status": result.status})
                            return
                        else:
                            it.status = "pending" if it.schedule_kind in ("interval", "daily") else "failed"
                        self._advance_after_run(it, now_utc)

                updated = self._find_and_update_job(job.job_id, _apply_done)
                coord.complete_request(
                    req_id,
                    {
                        "job_id": job.job_id,
                        "run_id": result.run_id,
                        "status": result.status,
                        "obsidian_note_id": note_id,
                        "telegram_notified": tg_sent,
                    },
                )
                return {
                    "job_id": job.job_id,
                    "run_id": result.run_id,
                    "status": updated.status if updated else result.status,
                    "loop_status": result.status,
                    "pending_approval_id": result.pending_approval_id,
                    "obsidian_note_id": note_id,
                    "telegram_notified": tg_sent,
                    "summary": result.summary,
                }
            except Exception as exc:
                coord.fail_request(req_id, str(exc))
                now_utc = _utc_now()

                def _apply_err(it: ScheduledGoal) -> None:
                    it.last_run_at = now_utc.isoformat()
                    it.last_status = "error"
                    it.last_error = str(exc)[:300]
                    it.status = "pending" if it.schedule_kind in ("interval", "daily") else "failed"
                    self._advance_after_run(it, now_utc)

                self._find_and_update_job(job.job_id, _apply_err)
                return {"job_id": job.job_id, "status": "failed", "error": str(exc)}
            finally:
                set_current_request_id(None)
                self._running_job_id = ""

    def trigger_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Immediately executes (or resumes if paused & decided) the specified job."""
        if not _agent_enabled():
            raise RuntimeError("Autonomous scheduler requires ZAINE_AGENT=1.")
        job = self.get_job(job_id)
        if job is None:
            return None
        resume_id = ""
        if job.status == "paused_approval" and job.last_run_id:
            resume_id = job.last_run_id
        return self._execute_job(job, resume_run_id=resume_id)

    def run_pending(self, *, now: Optional[_dt.datetime] = None) -> List[Dict[str, Any]]:
        """
        Checks for decided paused approvals and due scheduled/background jobs, executing them
        sequentially on the coordinator lock. Returns empty list immediately when ZAINE_AGENT=0.
        """
        if not _agent_enabled():
            return []

        now_utc = now if now is not None else _utc_now()
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=_dt.timezone.utc)

        outcomes: List[Dict[str, Any]] = []
        jobs = [ScheduledGoal.from_dict(r) for r in self._store.load_state().get("jobs") or []]

        # 1. Resume paused jobs only if an explicit human decision exists in ApprovalRegistry
        for job in jobs:
            if job.status != "paused_approval" or not job.pending_approval_id or not job.last_run_id:
                continue
            try:
                from approval import ApprovalRegistry
                prop = ApprovalRegistry.get_proposal(job.pending_approval_id)
            except Exception:
                prop = None
            prop_status = str((prop or {}).get("status") or "PENDING").upper()
            if prop_status in ("APPROVED", "DENIED", "CANCELLED", "EXPIRED"):
                outcomes.append(self._execute_job(job, resume_run_id=job.last_run_id))

        # Refresh job list after any resumed runs before dispatching fresh due jobs
        jobs = [ScheduledGoal.from_dict(r) for r in self._store.load_state().get("jobs") or []]
        for job in jobs:
            if not job.enabled or job.status != "pending":
                continue
            due_dt = _parse_iso_utc(job.next_run_at) if job.next_run_at else now_utc
            if due_dt is None or due_dt <= now_utc:
                outcomes.append(self._execute_job(job))

        return outcomes

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_pending()
            except Exception as exc:
                print(f"[SCHEDULER] Poll cycle error: {exc}", flush=True)
            if self._stop_event.wait(self._poll_interval_s):
                break

    def start(self) -> bool:
        """Starts the background polling worker thread when ZAINE_AGENT=1."""
        if not _agent_enabled():
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="ZaineGoalScheduler",
        )
        self._thread.start()
        return True

    def stop(self, timeout: float = 3.0) -> None:
        """Stops the background polling worker thread cleanly."""
        self._stop_event.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=max(0.1, float(timeout)))
        self._thread = None


_DEFAULT_SCHEDULER: Optional[GoalScheduler] = None
_SCHEDULER_SINGLETON_LOCK = threading.Lock()


def get_goal_scheduler() -> GoalScheduler:
    """Returns the process-wide GoalScheduler singleton."""
    global _DEFAULT_SCHEDULER
    if _DEFAULT_SCHEDULER is None:
        with _SCHEDULER_SINGLETON_LOCK:
            if _DEFAULT_SCHEDULER is None:
                _DEFAULT_SCHEDULER = GoalScheduler()
    return _DEFAULT_SCHEDULER


__all__ = [
    "GoalScheduler",
    "ScheduledGoal",
    "SchedulerStore",
    "VALID_SCHEDULE_KINDS",
    "compute_next_daily_run",
    "get_goal_scheduler",
    "get_quiet_status",
    "get_scheduler_dir",
    "is_quiet_mode",
    "record_quiet_suppression",
    "set_quiet_mode",
]

