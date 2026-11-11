"""
autonomy/scratchpad.py
Per-run crash-resumable scratchpad files (task, plan, progress, results) and optional
durable Obsidian episode flushing for Z.A.I.N.E autonomous runs.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_RESUMABLE_STATUSES = frozenset({"running", "paused", "cancelled", "stopped_timeout", "stopped_max_steps"})


def get_scratchpad_dir() -> Path:
    """Returns active directory for per-run crash-resume scratchpad JSON files."""
    raw = os.getenv("ZAINE_RUNS_DIR", "").strip()
    d = Path(raw) if raw else (PROJECT_ROOT / "data" / "runs")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitize_run_id(run_id: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(run_id or "").strip()).strip("._")
    if not clean or ".." in clean:
        raise ValueError(f"Invalid run_id for scratchpad: {run_id!r}")
    return clean


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


@dataclass
class RunScratchpad:
    """Durable per-run execution state supporting crash/restart recovery."""

    run_id: str
    task: str
    agent_id: str = "zaine-jarvis"
    workspace_dir: str = ""
    privacy_taint: str = "LOCAL_ONLY"
    status: str = "running"
    resumable: bool = True
    plan: List[str] = field(default_factory=list)
    current_step: int = 0
    max_steps: int = 8
    completed_steps: int = 0
    progress: List[Dict[str, Any]] = field(default_factory=list)
    results: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    final_summary: str = ""
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    pid: int = field(default_factory=os.getpid)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunScratchpad":
        fields = cls.__dataclass_fields__
        clean = {k: v for k, v in (data or {}).items() if k in fields}
        return cls(**clean)


class RunScratchpadStore:
    """Atomic filesystem store for per-run scratchpad JSON checkpoints."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else None

    @property
    def base_dir(self) -> Path:
        if self._base_dir is not None:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            return self._base_dir
        return get_scratchpad_dir()

    def path_for(self, run_id: str) -> Path:
        safe = _sanitize_run_id(run_id)
        root = self.base_dir.resolve()
        cand = (root / f"{safe}.json").resolve()
        if not cand.is_relative_to(root):
            raise ValueError(f"Scratchpad path traversal rejected for run_id={run_id!r}")
        return cand

    def save(self, pad: RunScratchpad) -> Path:
        pad.updated_at = _utc_now()
        pad.pid = os.getpid()
        if pad.status in _RESUMABLE_STATUSES:
            pad.resumable = True
        else:
            pad.resumable = False

        target = self.path_for(pad.run_id)
        payload = json.dumps(pad.to_dict(), indent=2, ensure_ascii=False)
        fd, tmp_name = tempfile.mkstemp(prefix=f"{target.stem}_", suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return target

    def load(self, run_id: str) -> Optional[RunScratchpad]:
        try:
            target = self.path_for(run_id)
        except ValueError:
            return None
        if not target.exists() or not target.is_file():
            return None
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            return RunScratchpad.from_dict(raw)
        except Exception:
            return None

    def list_runs(self, limit: int = 30, resumable_only: bool = False) -> List[Dict[str, Any]]:
        """Lists persisted runs newest-first, flagging crashed/dead-PID 'running' files as resumable."""
        try:
            from autonomy.cancel import get_active_runs

            active_ids = set(get_active_runs().keys())
        except Exception:
            active_ids = set()

        entries: List[Dict[str, Any]] = []
        root = self.base_dir
        for fp in root.glob("*.json"):
            try:
                raw = json.loads(fp.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or not raw.get("run_id"):
                    continue
                pad = RunScratchpad.from_dict(raw)
            except Exception:
                continue

            is_live_here = pad.run_id in active_ids
            crashed = (pad.status == "running") and (not is_live_here)
            if crashed and pad.pid == os.getpid():
                # Same PID is running this process, yet not registered in active_ids -> crashed/cleaned up
                crashed = True

            effective_status = "interrupted (resumable)" if crashed else pad.status
            is_resumable = bool(crashed or pad.status in ("paused", "cancelled", "stopped_timeout", "stopped_max_steps"))
            if resumable_only and not is_resumable:
                continue

            entries.append(
                {
                    "run_id": pad.run_id,
                    "task": pad.task[:160],
                    "agent_id": pad.agent_id,
                    "status": pad.status,
                    "effective_status": effective_status,
                    "resumable": is_resumable,
                    "crashed": crashed,
                    "completed_steps": pad.completed_steps,
                    "current_step": pad.current_step,
                    "max_steps": pad.max_steps,
                    "artifacts": list(pad.artifacts),
                    "privacy_taint": pad.privacy_taint,
                    "created_at": pad.created_at,
                    "updated_at": pad.updated_at,
                    "path": str(fp),
                }
            )

        entries.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return entries[: max(1, int(limit))]


def build_resume_context(pad: RunScratchpad, *, max_chars: int = 1600) -> str:
    """Formats a bounded resume briefing so the local 7B resumes cleanly without full replay."""
    lines: List[str] = [
        f"[RESUMED RUN {pad.run_id} | privacy={pad.privacy_taint}]",
        f"Goal: {pad.task}",
        f"Completed steps: {pad.completed_steps}/{pad.max_steps}",
    ]
    if pad.plan:
        lines.append("Plan progress:")
        for idx, step_text in enumerate(pad.plan, start=1):
            marker = "[done]" if idx <= pad.completed_steps else "[pending]"
            lines.append(f"  {idx}. {marker} {step_text[:120]}")
    if pad.results:
        lines.append("Recent tool results:")
        for item in pad.results[-3:]:
            preview = str(item.get("result", "")).strip().replace("\n", " ")[:160]
            lines.append(f"  - step {item.get('step')}: {item.get('tool')} [{item.get('status')}] -> {preview}")
    if pad.artifacts:
        lines.append("Artifacts so far: " + ", ".join(pad.artifacts[-6:]))
    if pad.errors:
        lines.append("Previous errors: " + "; ".join(str(e)[:120] for e in pad.errors[-2:]))

    block = "\n".join(lines)
    if len(block) > max_chars:
        return block[: max(0, max_chars - 3)].rstrip() + "..."
    return block


def flush_run_to_vault(pad: RunScratchpad, *, memory_manager: Optional[Any] = None) -> Optional[str]:
    """
    Persists a concise durable episode note in the Obsidian vault at provisional trust
    with LOCAL_ONLY privacy taint. Never promotes trust autonomously.
    """
    try:
        from memory_manager import get_memory_manager
        from memory_types import MemorySource, MemoryType, TrustLevel

        mm = memory_manager if memory_manager is not None else get_memory_manager()
        if mm is None or not mm.available:
            return None

        title = f"Run {pad.run_id}: {pad.task[:48]}"
        body = (
            f"Run ID: {pad.run_id}\n"
            f"Agent: {pad.agent_id}\n"
            f"Status: {pad.status}\n"
            f"Steps: {pad.completed_steps}/{pad.max_steps}\n"
            f"Artifacts: {', '.join(pad.artifacts) if pad.artifacts else 'None'}\n"
            f"Summary: {(pad.final_summary or '')[:600]}"
        )
        entry, _msg = mm.create(
            title=title,
            content=body,
            mem_type=MemoryType.EPISODE,
            source=MemorySource.AGENT_INFERENCE,
            trust=TrustLevel.PROVISIONAL,
            privacy_taint=pad.privacy_taint or "LOCAL_ONLY",
            tags=["autonomous-run", pad.status],
            source_ref=f"scratchpad:{pad.run_id}",
        )
        return entry.id if entry is not None else None
    except Exception:
        return None

