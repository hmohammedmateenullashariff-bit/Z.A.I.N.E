"""
autonomy
Bounded autonomous agent execution layer for Project-Z (Z.A.I.N.E).

Gated behind ZAINE_AGENT=1 (default OFF). When ZAINE_AGENT=0, Z.A.I.N.E runs
its original single-turn/legacy path unchanged.
"""

import os

from autonomy.tool_validation import (
    ToolValidationResult,
    looks_like_tool_attempt,
    validate_and_repair_tool_calls,
)
from autonomy.loop import (
    AutonomousLoop,
    CancelToken,
    LoopConfig,
    LoopResult,
    StepRecord,
    cancel_run,
    get_active_runs,
    register_active_run,
    unregister_active_run,
)


def is_agent_enabled() -> bool:
    """Returns True when the autonomous agent layer is enabled via ZAINE_AGENT=1."""
    return os.getenv("ZAINE_AGENT", "0").strip().lower() in ("1", "true", "yes", "on")


__all__ = [
    "is_agent_enabled",
    "AutonomousLoop",
    "CancelToken",
    "LoopConfig",
    "LoopResult",
    "StepRecord",
    "ToolValidationResult",
    "looks_like_tool_attempt",
    "validate_and_repair_tool_calls",
    "register_active_run",
    "unregister_active_run",
    "cancel_run",
    "get_active_runs",
]

