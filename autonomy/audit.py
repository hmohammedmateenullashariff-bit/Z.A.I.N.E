"""
autonomy/audit.py
Per-run JSON audit trail for ZAINE_AGENT=1 autonomous executions.

Records every step/tool invocation (agent, tool, redacted args summary, result,
approval decisions, timestamps) into atomic JSON files under data/audit/<run_id>.json
(or ZAINE_AUDIT_DIR). Parent and subagent delegations append sequentially to the
parent run's audit log via a ContextVar scope.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from autonomy.scratchpad import atomic_write_json, sanitize_run_id, utc_now_iso
from harness import compact

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_SENSITIVE_KEY_TOKENS = ("token", "secret", "password", "passwd", "api_key", "apikey", "credential", "authorization")
_ACTIVE_RECORDER: ContextVar[Optional["RunAuditRecorder"]] = ContextVar("zaine_active_audit_recorder", default=None)
_STEP_APPROVAL_DECISIONS: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar(
    "zaine_step_approval_decisions",
    default=None,
)


def get_audit_dir() -> Path:
    """Returns directory for per-run JSON audit files (ZAINE_AUDIT_DIR or data/audit)."""
    raw = os.getenv("ZAINE_AUDIT_DIR", "").strip()
    root = Path(raw) if raw else (PROJECT_ROOT / "data" / "audit")
    root.mkdir(parents=True, exist_ok=True)
    return root


def summarize_args(args: Any, max_chars: int = 260) -> str:
    """Formats a bounded, secret-redacted summary of tool arguments."""
    if args is None:
        return ""
    if not isinstance(args, dict):
        raw = str(args).replace("\r", " ").replace("\n", " ").strip()
        return raw if len(raw) <= max_chars else raw[: max(0, max_chars - 3)].rstrip() + "..."

    parts: List[str] = []
    for k, v in args.items():
        key = str(k)
        low_k = key.lower()
        if any(tok in low_k for tok in _SENSITIVE_KEY_TOKENS):
            parts.append(f"{key}=<redacted>")
            continue
        if isinstance(v, str):
            clean = v.replace("\r", " ").replace("\n", "\\n")
            if low_k in ("content", "python_code", "new_str", "old_str", "diff") and len(clean) > 80:
                parts.append(f"{key}=<{len(v)} chars: {clean[:48]}...>")
            elif len(clean) > 80:
                parts.append(f"{key}={clean[:77]!r}...")
            else:
                parts.append(f"{key}={clean!r}")
        else:
            rep = repr(v)
            if len(rep) > 80:
                rep = rep[:77] + "..."
            parts.append(f"{key}={rep}")

    joined = ", ".join(parts)
    if len(joined) <= max_chars:
        return joined
    return joined[: max(0, max_chars - 3)].rstrip() + "..."


def summarize_result(result: Any, max_chars: int = 400) -> str:
    """Returns a bounded single-line/compact preview of a tool result for audit storage."""
    text = str(result or "").strip()
    if not text:
        return ""
    compacted, _ = compact(text, max_chars)
    return compacted[:max_chars]


@dataclass
class ApprovalDecisionRecord:
    """Represents a single security/approval evaluation during an autonomous run."""

    timestamp: str
    agent: str
    tool: str
    action_type: str
    risk_level: str
    decision: str
    proposal_id: str = ""
    note: str = ""
    target_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditEntry:
    """Represents one audited tool call or permission block within a run."""

    seq: int
    timestamp: str
    agent: str
    delegation_depth: int
    step: int
    tool: str
    args_summary: str
    result_status: str
    result_summary: str
    approval_decision: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunAuditLog:
    """Complete per-run JSON audit trail document."""

    run_id: str
    task: str
    root_agent_id: str = "zaine-jarvis"
    model_name: str = ""
    status: str = "running"
    stop_reason: str = ""
    privacy_taint: str = "LOCAL_ONLY"
    started_at: str = field(default_factory=utc_now_iso)
    ended_at: Optional[str] = None
    updated_at: str = field(default_factory=utc_now_iso)
    duration_s: Optional[float] = None
    steps_executed: int = 0
    max_steps: int = 0
    artifacts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    approval_decisions: List[Dict[str, Any]] = field(default_factory=list)
    entries: List[Dict[str, Any]] = field(default_factory=list)
    schema_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunAuditLog":
        fields = cls.__dataclass_fields__
        clean = {k: v for k, v in (data or {}).items() if k in fields}
        return cls(**clean)


class AuditLogStore:
    """Atomic filesystem store for per-run JSON audit files."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else None

    @property
    def base_dir(self) -> Path:
        if self._base_dir is not None:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            return self._base_dir
        return get_audit_dir()

    def path_for(self, run_id: str) -> Path:
        safe = sanitize_run_id(run_id)
        root = self.base_dir.resolve()
        cand = (root / f"{safe}.json").resolve()
        if not cand.is_relative_to(root):
            raise ValueError(f"Audit path traversal rejected for run_id={run_id!r}")
        return cand

    def save(self, audit: RunAuditLog) -> Path:
        audit.updated_at = utc_now_iso()
        target = self.path_for(audit.run_id)
        return atomic_write_json(target, audit.to_dict())

    def load(self, run_id: str) -> Optional[RunAuditLog]:
        try:
            target = self.path_for(run_id)
        except ValueError:
            return None
        if not target.exists() or not target.is_file():
            return None
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not raw.get("run_id"):
                return None
            return RunAuditLog.from_dict(raw)
        except Exception:
            return None

    def list_audits(self, limit: int = 30) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for fp in self.base_dir.glob("*.json"):
            try:
                raw = json.loads(fp.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or not raw.get("run_id"):
                    continue
                items.append(
                    {
                        "run_id": raw.get("run_id"),
                        "task": str(raw.get("task") or "")[:160],
                        "root_agent_id": raw.get("root_agent_id", "zaine-jarvis"),
                        "model_name": raw.get("model_name", ""),
                        "status": raw.get("status", "unknown"),
                        "privacy_taint": raw.get("privacy_taint", "LOCAL_ONLY"),
                        "steps_executed": raw.get("steps_executed", 0),
                        "max_steps": raw.get("max_steps", 0),
                        "entry_count": len(raw.get("entries") or []),
                        "approval_count": len(raw.get("approval_decisions") or []),
                        "started_at": raw.get("started_at", ""),
                        "ended_at": raw.get("ended_at"),
                        "updated_at": raw.get("updated_at", ""),
                        "path": str(fp),
                    }
                )
            except Exception:
                continue
        items.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return items[: max(1, int(limit))]


def _select_primary_approval(decisions: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Selects the authoritative approval decision for a single tool invocation."""
    if not decisions:
        return {"decision": "NOT_REQUIRED", "proposal_id": "", "note": "", "timestamp": utc_now_iso()}
    for item in decisions:
        if item.get("decision") not in ("PREAPPROVED", "NOT_REQUIRED"):
            return dict(item)
    return dict(decisions[0])


class RunAuditRecorder:
    """Thread-safe incremental audit writer bound to a single root autonomous run."""

    def __init__(
        self,
        log: RunAuditLog,
        store: Optional[AuditLogStore] = None,
    ) -> None:
        self.log = log
        self.store = store or AuditLogStore()
        self._lock = threading.Lock()
        self.audit_path: Optional[Path] = None

    @classmethod
    def open_for_run(
        cls,
        *,
        run_id: str,
        task: str,
        root_agent_id: str,
        model_name: str,
        max_steps: int,
        privacy_taint: str = "LOCAL_ONLY",
        store: Optional[AuditLogStore] = None,
        resume: bool = False,
    ) -> "RunAuditRecorder":
        active_store = store or AuditLogStore()
        existing = active_store.load(run_id) if resume else None
        if existing is not None:
            existing.status = "running"
            existing.ended_at = None
            existing.max_steps = max(int(existing.max_steps or 0), int(max_steps or 0))
            log = existing
        else:
            log = RunAuditLog(
                run_id=run_id,
                task=task,
                root_agent_id=root_agent_id or "zaine-jarvis",
                model_name=model_name or "",
                status="running",
                privacy_taint=privacy_taint or "LOCAL_ONLY",
                max_steps=int(max_steps or 0),
            )
        rec = cls(log=log, store=active_store)
        rec.flush()
        return rec

    def flush(self) -> Optional[Path]:
        with self._lock:
            try:
                self.audit_path = self.store.save(self.log)
            except Exception:
                return self.audit_path
            return self.audit_path

    def record_approval(
        self,
        *,
        agent: str,
        tool: str,
        action_type: str,
        risk_level: str,
        decision: str,
        proposal_id: str = "",
        note: str = "",
        target_summary: str = "",
    ) -> ApprovalDecisionRecord:
        rec = ApprovalDecisionRecord(
            timestamp=utc_now_iso(),
            agent=agent or self.log.root_agent_id,
            tool=tool,
            action_type=action_type,
            risk_level=risk_level,
            decision=decision,
            proposal_id=proposal_id,
            note=(note or "")[:300],
            target_summary=(target_summary or "")[:200],
        )
        rec_dict = rec.to_dict()
        with self._lock:
            self.log.approval_decisions.append(rec_dict)
            try:
                self.audit_path = self.store.save(self.log)
            except Exception:
                pass
        step_bucket = _STEP_APPROVAL_DECISIONS.get(None)
        if step_bucket is not None:
            step_bucket.append(rec_dict)
        return rec

    def record_tool_call(
        self,
        *,
        agent: str,
        delegation_depth: int,
        step: int,
        tool: str,
        args: Any,
        result: Any,
        result_status: str,
        duration_ms: Optional[float] = None,
        approval_decision: Optional[Dict[str, Any]] = None,
        step_approvals: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Path]:
        chosen_approval = approval_decision if approval_decision is not None else _select_primary_approval(step_approvals)
        with self._lock:
            seq = len(self.log.entries) + 1
            entry = AuditEntry(
                seq=seq,
                timestamp=utc_now_iso(),
                agent=agent or self.log.root_agent_id,
                delegation_depth=int(delegation_depth or 0),
                step=int(step or 0),
                tool=tool,
                args_summary=summarize_args(args),
                result_status=result_status,
                result_summary=summarize_result(result),
                approval_decision=dict(chosen_approval),
                duration_ms=round(float(duration_ms), 2) if duration_ms is not None else None,
            )
            self.log.entries.append(entry.to_dict())
            try:
                self.audit_path = self.store.save(self.log)
            except Exception:
                pass
            return self.audit_path

    def finalize(
        self,
        *,
        status: str,
        stop_reason: str = "",
        duration_s: Optional[float] = None,
        steps_executed: int = 0,
        max_steps: int = 0,
        artifacts: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
        privacy_taint: str = "LOCAL_ONLY",
    ) -> Optional[Path]:
        with self._lock:
            self.log.status = status
            self.log.stop_reason = (stop_reason or "")[:500]
            self.log.ended_at = utc_now_iso()
            self.log.duration_s = round(float(duration_s), 3) if duration_s is not None else self.log.duration_s
            self.log.steps_executed = max(int(self.log.steps_executed or 0), int(steps_executed or 0))
            if max_steps:
                self.log.max_steps = max(int(self.log.max_steps or 0), int(max_steps))
            if artifacts is not None:
                self.log.artifacts = list(artifacts)
            if errors is not None:
                self.log.errors = list(errors)
            if privacy_taint:
                self.log.privacy_taint = privacy_taint
            try:
                self.audit_path = self.store.save(self.log)
            except Exception:
                pass
            return self.audit_path


def get_active_audit_recorder() -> Optional[RunAuditRecorder]:
    """Returns the RunAuditRecorder active in the current ContextVar scope, or None."""
    return _ACTIVE_RECORDER.get(None)


@contextmanager
def active_audit_recorder(recorder: Optional[RunAuditRecorder]) -> Iterator[Optional[RunAuditRecorder]]:
    """Binds a RunAuditRecorder for the duration of a root autonomous run."""
    tok = _ACTIVE_RECORDER.set(recorder)
    try:
        yield recorder
    finally:
        _ACTIVE_RECORDER.reset(tok)


@contextmanager
def capture_step_approvals() -> Iterator[List[Dict[str, Any]]]:
    """Captures approval decisions evaluated during one tool execution step cleanly."""
    bucket: List[Dict[str, Any]] = []
    tok = _STEP_APPROVAL_DECISIONS.set(bucket)
    try:
        yield bucket
    finally:
        _STEP_APPROVAL_DECISIONS.reset(tok)

