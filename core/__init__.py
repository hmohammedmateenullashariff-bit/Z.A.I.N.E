"""
core/
Modular core systems for Project-Z (Z.A.I.N.E).
Includes:
- circuit_breaker: Deterministic keyed circuit breaker and fail-to-reflect logging
- task_envelope: Typed immutable subagent task and result contracts
"""

from core.circuit_breaker import (
    CircuitState,
    CircuitBreakerManager,
    get_circuit_breaker
)
from core.task_envelope import (
    TaskEnvelope,
    ResultEnvelope,
    is_tool_permitted,
    current_agent_var,
    current_envelope_var
)
from core.job_supervisor import (
    JobStatus,
    JobRecord,
    JobSupervisor,
    get_job_supervisor
)

__all__ = [
    "CircuitState",
    "CircuitBreakerManager",
    "get_circuit_breaker",
    "TaskEnvelope",
    "ResultEnvelope",
    "is_tool_permitted",
    "current_agent_var",
    "current_envelope_var",
    "JobStatus",
    "JobRecord",
    "JobSupervisor",
    "get_job_supervisor"
]
