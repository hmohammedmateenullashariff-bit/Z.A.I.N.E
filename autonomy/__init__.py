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
from autonomy.privacy import (
    PrivacyViolationError,
    SessionPrivacyState,
    assert_local_routing,
    check_outbound_cloud_block,
    get_privacy_state,
    is_cloud_endpoint,
    is_session_private,
    mark_session_private,
    reset_privacy_session,
    scoped_privacy_session,
)
from autonomy.memory_review import (
    approve_review_item,
    compute_fact_fingerprint,
    init_memory_review_schema,
    list_review_queue,
    record_agent_fact,
    reject_review_item,
    submit_fact_candidate,
)
from autonomy.memory_bridge import (
    MAX_MEMORY_BUDGET_CHARS,
    extract_step_keywords,
    retrieve_step_memory,
)
from autonomy.scratchpad import (
    RunScratchpad,
    RunScratchpadStore,
    build_resume_context,
    flush_run_to_vault,
    get_scratchpad_dir,
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
    "MAX_MEMORY_BUDGET_CHARS",
    "MESSAGING_TOOLS",
    "NETWORK_TOOLS",
    "PrivacyViolationError",
    "RunScratchpad",
    "RunScratchpadStore",
    "SHELL_TOOLS",
    "SessionPrivacyState",
    "StepRecord",
    "ToolValidationResult",
    "UNTRUSTED_SOURCE_TOOLS",
    "approve_review_item",
    "assert_local_routing",
    "build_resume_context",
    "build_scoped_context",
    "cancel_run",
    "check_outbound_cloud_block",
    "compute_fact_fingerprint",
    "compute_unified_diff",
    "contains_injection_attempt",
    "current_delegation_depth",
    "describe_side_effect",
    "emit_diff_preview",
    "execute_delegate",
    "extract_injected_tool_names",
    "extract_step_keywords",
    "flush_run_to_vault",
    "get_active_runs",
    "get_privacy_state",
    "get_scratchpad_dir",
    "init_memory_review_schema",
    "is_cloud_endpoint",
    "is_sensitive_path",
    "is_session_private",
    "is_tool_preapproved",
    "is_write_blocked_path",
    "list_review_queue",
    "looks_like_tool_attempt",
    "mark_session_private",
    "preapproved_tool_scope",
    "precheck_external_write",
    "read_outside_workspace",
    "record_agent_fact",
    "register_active_run",
    "reject_review_item",
    "require_side_effect_approval",
    "reset_privacy_session",
    "resolve_external_path",
    "resolve_sandbox_path",
    "resolve_subagent_profile",
    "retrieve_step_memory",
    "run_subagent_delegation",
    "sanitize_untrusted_text",
    "scoped_privacy_session",
    "submit_fact_candidate",
    "unregister_active_run",
    "validate_and_repair_tool_calls",
    "wrap_untrusted_content",
    "write_outside_workspace",
]

