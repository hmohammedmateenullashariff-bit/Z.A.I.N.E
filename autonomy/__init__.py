"""
autonomy
Bounded autonomous agent execution layer for Project-Z (Z.A.I.N.E).

Gated behind ZAINE_AGENT=1 (default OFF). When ZAINE_AGENT=0, Z.A.I.N.E runs
its original single-turn/legacy path unchanged.
"""

import os


def is_agent_enabled() -> bool:
    """Returns True when the autonomous agent layer is enabled via ZAINE_AGENT=1."""
    return os.getenv("ZAINE_AGENT", "0").strip().lower() in ("1", "true", "yes", "on")


from autonomy.tool_validation import (
    ToolValidationResult,
    looks_like_tool_attempt,
    validate_and_repair_tool_calls,
)
from autonomy.cancel import (
    CancelToken,
    cancel_run,
    get_active_runs,
    register_active_run,
    unregister_active_run,
)
from autonomy.guards import (
    EXTERNAL_WRITE_TOOLS,
    MESSAGING_TOOLS,
    NETWORK_TOOLS,
    SHELL_TOOLS,
    describe_side_effect,
    is_tool_preapproved,
    preapproved_tool_scope,
    require_side_effect_approval,
)
from autonomy.sandbox import (
    compute_unified_diff,
    emit_diff_preview,
    is_sensitive_path,
    is_write_blocked_path,
    precheck_external_write,
    read_outside_workspace,
    resolve_external_path,
    resolve_sandbox_path,
    write_outside_workspace,
)
from autonomy.untrusted import (
    UNTRUSTED_SOURCE_TOOLS,
    contains_injection_attempt,
    extract_injected_tool_names,
    sanitize_untrusted_text,
    wrap_untrusted_content,
)
from autonomy.loop import (
    AutonomousLoop,
    LoopConfig,
    LoopResult,
    StepRecord,
)
from autonomy.subagents import (
    DelegationResult,
    MAX_DELEGATION_DEPTH,
    build_scoped_context,
    current_delegation_depth,
    execute_delegate,
    resolve_subagent_profile,
    run_subagent_delegation,
)


__all__ = [
    "is_agent_enabled",
    "AutonomousLoop",
    "CancelToken",
    "DelegationResult",
    "EXTERNAL_WRITE_TOOLS",
    "LoopConfig",
    "LoopResult",
    "MAX_DELEGATION_DEPTH",
    "MESSAGING_TOOLS",
    "NETWORK_TOOLS",
    "SHELL_TOOLS",
    "StepRecord",
    "ToolValidationResult",
    "UNTRUSTED_SOURCE_TOOLS",
    "build_scoped_context",
    "cancel_run",
    "compute_unified_diff",
    "contains_injection_attempt",
    "current_delegation_depth",
    "describe_side_effect",
    "emit_diff_preview",
    "execute_delegate",
    "extract_injected_tool_names",
    "get_active_runs",
    "is_sensitive_path",
    "is_tool_preapproved",
    "is_write_blocked_path",
    "looks_like_tool_attempt",
    "preapproved_tool_scope",
    "precheck_external_write",
    "read_outside_workspace",
    "register_active_run",
    "require_side_effect_approval",
    "resolve_external_path",
    "resolve_sandbox_path",
    "resolve_subagent_profile",
    "run_subagent_delegation",
    "sanitize_untrusted_text",
    "unregister_active_run",
    "validate_and_repair_tool_calls",
    "wrap_untrusted_content",
    "write_outside_workspace",
]

