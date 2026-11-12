"""
autonomy/guards.py
Centralized side-effect approval gating for ZAINE_AGENT=1 autonomous execution.

Side-effecting operations (shell commands, package installs, network fetch, messaging)
always pause for explicit human authorization via approval.require_approval(), and never
auto-approve in unattended runs.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import inspect
import os
import re
from typing import Any, Dict, FrozenSet, Iterator, Optional, Tuple

_PROPOSAL_ID_RE = re.compile(r"\b(ACT-[0-9A-F]{6,16})\b", re.I)


def _record_audit_approval(
    *,
    tool_name: str,
    action_type: str,
    risk_level: str,
    decision: str,
    proposal_id: str = "",
    note: str = "",
    target_summary: str = "",
) -> None:
    """Records an approval/security gate decision into the active RunAuditRecorder if bound."""
    try:
        from autonomy.audit import get_active_audit_recorder
        from core.task_envelope import current_agent_var

        recorder = get_active_audit_recorder()
        if recorder is None:
            return
        agent_id = current_agent_var.get(None) or recorder.log.root_agent_id or "zaine-jarvis"
        recorder.record_approval(
            agent=str(agent_id),
            tool=tool_name,
            action_type=action_type,
            risk_level=risk_level,
            decision=decision,
            proposal_id=proposal_id,
            note=note,
            target_summary=target_summary,
        )
    except Exception:
        pass

_PREAPPROVED_TOOL: ContextVar[Optional[str]] = ContextVar("zaine_preapproved_tool", default=None)

SHELL_TOOLS: FrozenSet[str] = frozenset({"execute_command", "install_python_package"})
EXTERNAL_WRITE_TOOLS: FrozenSet[str] = frozenset({"write_external_file", "create_custom_tool"})
NETWORK_TOOLS: FrozenSet[str] = frozenset(
    {
        "browse_web",
        "search_web",
        "search_and_extract",
        "download_web_file",
        "query_public_api",
        "open_url",
    }
)
MESSAGING_TOOLS: FrozenSet[str] = frozenset({"send_email", "upload_youtube_video"})


def is_tool_preapproved(tool_name: str) -> bool:
    """Returns True inside the immediate execution scope after AutonomousLoop obtained approval."""
    cur = _PREAPPROVED_TOOL.get(None)
    if cur is None:
        return False
    if isinstance(cur, (tuple, list, set, frozenset)):
        return tool_name in cur
    if cur == tool_name:
        return True
    # search_and_extract internally calls browse_web; inherit approval across that single call
    if cur == "search_and_extract" and tool_name == "browse_web":
        return True
    return False


@contextmanager
def preapproved_tool_scope(tool_name: Any) -> Iterator[None]:
    """Marks a single tool (or explicit resumed tool set) as already approved for internal calls."""
    val = tuple(tool_name) if isinstance(tool_name, (list, tuple, set, frozenset)) else tool_name
    tok = _PREAPPROVED_TOOL.set(val)
    try:
        yield
    finally:
        _PREAPPROVED_TOOL.reset(tok)


def describe_side_effect(tool_name: str, args: Dict[str, Any]) -> Optional[Tuple[str, str, str, str]]:
    """
    Returns (action_type, risk_level, title, payload_summary) if `tool_name` requires
    explicit approval under ZAINE_AGENT=1, or None for read-only / workspace-safe tools.
    """
    t = (tool_name or "").strip()
    if t == "execute_command":
        cmd = str(args.get("command") or "")
        low = cmd.lower()
        if any(k in low for k in ("| sh", "| bash", "iex", "downloadstring", "invoke-expression")):
            risk = "Critical"
        elif any(k in low for k in ("pip ", "npm ", "npx ", "rm ", "del ")):
            risk = "High"
        else:
            risk = "Moderate"
        return ("COMMAND", risk, f"Execute shell command: {cmd[:60]}", cmd)
    if t == "install_python_package":
        pkg = str(args.get("package_name") or args.get("package") or "")
        return ("PACKAGE_INSTALL", "High", f"Install Python package: {pkg[:60]}", f"pip install {pkg}")
    if t == "create_custom_tool":
        tool_id = str(args.get("tool_name") or "custom_tool")
        code = str(args.get("python_code") or "")
        return ("CUSTOM_TOOL_WRITE", "High", f"Synthesize & write custom tool: {tool_id[:60]}", code[:450] or tool_id)
    if t == "write_external_file":
        fpath = str(args.get("filepath") or args.get("path") or "")
        diff_txt = str(args.get("diff") or "")
        is_overwrite = bool(args.get("is_overwrite"))
        verb = "Overwrite" if is_overwrite else "Write"
        summary_body = diff_txt[:450] if diff_txt else fpath
        return ("EXTERNAL_FILE_WRITE", "High", f"{verb} external file: {fpath[:60]}", summary_body)
    if t == "run_python_script_external":
        script_path = str(args.get("script_path") or "")
        return ("COMMAND", "Moderate", f"Execute outside-workspace script: {script_path[:60]}", script_path)
    if t in NETWORK_TOOLS:
        target = str(args.get("url") or args.get("query") or args.get("endpoint_url") or t)
        return ("NETWORK_FETCH", "Moderate", f"Network access ({t}): {target[:60]}", target)
    if t in MESSAGING_TOOLS:
        target = str(args.get("to_email") or args.get("title") or t)
        return ("EXTERNAL_MESSAGE", "High", f"Send external message ({t}): {target[:60]}", str(args)[:300])
    if t == "access_social_platform" and str(args.get("action", "")).lower() == "post":
        return ("EXTERNAL_MESSAGE", "High", "Publish social media post", str(args)[:300])
    return None


def require_side_effect_approval(tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Enforces blocking human approval through approval.require_approval().
    Returns (True, "not_required" | "Approved: ...") or (False, "[APPROVAL REQUIRED / DENIED]: ...").
    """
    from autonomy.privacy import check_outbound_cloud_block

    effective_args = dict(args or {})
    cloud_block = check_outbound_cloud_block(tool_name, effective_args)
    if cloud_block:
        _record_audit_approval(
            tool_name=tool_name,
            action_type="PRIVACY_POLICY",
            risk_level="High",
            decision="BLOCKED_PRIVACY",
            note=cloud_block,
            target_summary=str(effective_args)[:180],
        )
        return False, cloud_block

    if is_tool_preapproved(tool_name):
        if _PREAPPROVED_TOOL.get(None) != tool_name:
            _record_audit_approval(
                tool_name=tool_name,
                action_type="DELEGATED_SCOPE",
                risk_level="Moderate",
                decision="PREAPPROVED",
                note=f"Inherited single-call approval from '{_PREAPPROVED_TOOL.get(None)}'",
                target_summary=str(effective_args)[:180],
            )
        return True, "preapproved"

    if (tool_name or "").strip() == "write_external_file":
        from autonomy.sandbox import emit_diff_preview, precheck_external_write

        raw_fp = str(effective_args.get("filepath") or effective_args.get("path") or "")
        content = str(effective_args.get("content") or "")
        target, diff_text, is_overwrite, block_err = precheck_external_write(raw_fp, content)
        if block_err or target is None:
            reason = block_err or f"External write to '{raw_fp}' was blocked."
            _record_audit_approval(
                tool_name=tool_name,
                action_type="EXTERNAL_FILE_WRITE",
                risk_level="High",
                decision="BLOCKED_SANDBOX",
                note=reason,
                target_summary=raw_fp[:180],
            )
            return False, reason
        effective_args["filepath"] = str(target)
        effective_args["diff"] = diff_text
        effective_args["is_overwrite"] = is_overwrite
        if diff_text:
            emit_diff_preview("write_external_file", str(target), diff_text, is_overwrite=is_overwrite)

    spec = describe_side_effect(tool_name, effective_args)
    if spec is None:
        return True, "not_required"

    action_type, risk_level, title, payload = spec
    import approval as _approval_mod

    pop_meta = getattr(_approval_mod, "pop_last_approval_decision", None)
    if callable(pop_meta):
        pop_meta()

    unattended = is_unattended_run()
    req_kwargs: Dict[str, Any] = {
        "action_type": action_type,
        "title": title,
        "description": f"Autonomous agent requests '{tool_name}': {payload[:240]}",
        "code_or_cmd": payload[:500],
        "explanation": (
            f"Safety gate: '{tool_name}' ({action_type}) has side effects beyond the read-only/sandbox boundary "
            "and requires explicit operator authorization."
        ),
        "risk_level": risk_level,
        "tool_name": tool_name,
    }
    if unattended:
        try:
            sig_params = inspect.signature(_approval_mod.require_approval).parameters
            if "timeout_seconds" in sig_params:
                req_kwargs["timeout_seconds"] = max(0, int(get_unattended_approval_wait_s()))
            if "leave_pending_on_timeout" in sig_params:
                req_kwargs["leave_pending_on_timeout"] = True
        except (TypeError, ValueError):
            pass

    ok, msg = _approval_mod.require_approval(**req_kwargs)

    meta = pop_meta() if callable(pop_meta) else None
    proposal_id = ""
    if isinstance(meta, dict):
        proposal_id = str(meta.get("proposal_id") or "")
        raw_st = str(meta.get("status") or "").upper()
        decision = "EXPIRED" if raw_st == "TIMEOUT" else (raw_st or ("APPROVED" if ok else "DENIED"))
    else:
        m = _PROPOSAL_ID_RE.search(str(msg or ""))
        if m:
            proposal_id = m.group(1).upper()
        low_msg = str(msg or "").lower()
        if ok:
            decision = "APPROVED"
        elif "paused" in low_msg:
            decision = "PAUSED"
        elif "expired" in low_msg or "timeout" in low_msg:
            decision = "EXPIRED"
        elif "cancel" in low_msg:
            decision = "CANCELLED"
        else:
            decision = "DENIED"

    if unattended and not ok and (
        decision in ("PAUSED", "EXPIRED") or "paused awaiting approval" in str(msg or "").lower()
    ):
        if not proposal_id:
            m = _PROPOSAL_ID_RE.search(str(msg or ""))
            if m:
                proposal_id = m.group(1).upper()
        if not proposal_id:
            try:
                latest = _approval_mod.ApprovalRegistry.get_latest_pending()
                if latest and latest.get("id"):
                    proposal_id = str(latest["id"])
            except Exception:
                pass
        _record_audit_approval(
            tool_name=tool_name,
            action_type=action_type,
            risk_level=risk_level,
            decision="PAUSED_FOR_APPROVAL",
            proposal_id=proposal_id,
            note=str(msg or ""),
            target_summary=payload[:180],
        )
        raise ApprovalPauseRequested(
            proposal_id=proposal_id,
            tool_name=tool_name,
            args=dict(effective_args),
            reason=str(msg or ""),
            action_type=action_type,
            risk_level=risk_level,
        )

    _record_audit_approval(
        tool_name=tool_name,
        action_type=action_type,
        risk_level=risk_level,
        decision=decision,
        proposal_id=proposal_id,
        note=str(msg or ""),
        target_summary=payload[:180],
    )
    if not ok:
        return False, f"Approval required / denied for '{tool_name}': {msg}"
    return True, msg


_UNATTENDED_CONTEXT: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "zaine_unattended_run_ctx",
    default=None,
)


class ApprovalPauseRequested(Exception):
    """Raised when an unattended run pauses for explicit human authorization."""

    def __init__(
        self,
        *,
        proposal_id: str,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        reason: str = "",
        action_type: str = "",
        risk_level: str = "Moderate",
    ) -> None:
        self.proposal_id = str(proposal_id or "")
        self.tool_name = str(tool_name or "")
        self.tool_args = dict(args or {})
        self.reason = str(reason or "")
        self.action_type = str(action_type or "")
        self.risk_level = str(risk_level or "Moderate")
        super().__init__(
            f"Approval pause requested ({self.proposal_id or 'PENDING'}) for '{self.tool_name}': {self.reason}"
        )


def is_unattended_run() -> bool:
    """Returns True when executing inside an unattended background/scheduled run."""
    ctx = _UNATTENDED_CONTEXT.get()
    return bool(ctx and ctx.get("pause_on_approval", True))


def get_unattended_approval_wait_s() -> float:
    """Seconds an unattended run waits before yielding into a paused approval state (default 0)."""
    ctx = _UNATTENDED_CONTEXT.get()
    if ctx and "approval_wait_s" in ctx:
        try:
            return max(0.0, float(ctx["approval_wait_s"]))
        except Exception:
            return 0.0
    try:
        return max(0.0, float(os.getenv("ZAINE_BG_APPROVAL_WAIT_S", "0") or "0"))
    except Exception:
        return 0.0


@contextmanager
def unattended_run_scope(
    *,
    pause_on_approval: bool = True,
    approval_wait_s: Optional[float] = None,
) -> Iterator[None]:
    """Marks the active context as unattended so risky actions pause cleanly without auto-approving."""
    wait_s = approval_wait_s
    if wait_s is None:
        try:
            wait_s = max(0.0, float(os.getenv("ZAINE_BG_APPROVAL_WAIT_S", "0") or "0"))
        except Exception:
            wait_s = 0.0
    tok = _UNATTENDED_CONTEXT.set(
        {
            "pause_on_approval": bool(pause_on_approval),
            "approval_wait_s": max(0.0, float(wait_s)),
        }
    )
    try:
        yield
    finally:
        _UNATTENDED_CONTEXT.reset(tok)
