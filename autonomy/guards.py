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
from typing import Any, Dict, FrozenSet, Iterator, Optional, Tuple

_PREAPPROVED_TOOL: ContextVar[Optional[str]] = ContextVar("zaine_preapproved_tool", default=None)

SHELL_TOOLS: FrozenSet[str] = frozenset({"execute_command", "install_python_package"})
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
    if cur == tool_name:
        return True
    # search_and_extract internally calls browse_web; inherit approval across that single call
    if cur == "search_and_extract" and tool_name == "browse_web":
        return True
    return False


@contextmanager
def preapproved_tool_scope(tool_name: str) -> Iterator[None]:
    """Marks a single tool invocation as already approved for its internal helper calls."""
    tok = _PREAPPROVED_TOOL.set(tool_name)
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
    if is_tool_preapproved(tool_name):
        return True, "preapproved"

    spec = describe_side_effect(tool_name, args)
    if spec is None:
        return True, "not_required"

    action_type, risk_level, title, payload = spec
    from approval import require_approval

    ok, msg = require_approval(
        action_type=action_type,
        title=title,
        description=f"Autonomous agent requests '{tool_name}': {payload[:240]}",
        code_or_cmd=payload[:500],
        explanation=(
            f"Safety gate: '{tool_name}' ({action_type}) has side effects beyond the read-only/sandbox boundary "
            "and requires explicit operator authorization."
        ),
        risk_level=risk_level,
        tool_name=tool_name,
    )
    if not ok:
        return False, f"Approval required / denied for '{tool_name}': {msg}"
    return True, msg
