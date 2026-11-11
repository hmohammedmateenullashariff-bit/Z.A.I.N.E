"""
core/task_envelope.py
Typed, validated task envelopes and context isolation for Sub-Agent delegation in Project-Z.
Implements Claude Sonnet 5.5 backend criteria:
- Isolation is built into data structures: no conversation history is passed.
- Explicit pointer allowlists (file paths, note IDs) rather than raw message injection.
- Length-validated brief (<= 120 tokens / 600 chars).
- ResultEnvelope with taint tracking, tool execution log, and patch hashes.
- ContextVar-based tool permission gating across worker execution threads.
"""

import contextvars
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("zaine.core.task_envelope")

# Context variables carried across async / worker tasks
current_agent_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_agent", default="zaine-core"
)
current_envelope_var: contextvars.ContextVar[Optional["TaskEnvelope"]] = contextvars.ContextVar(
    "current_envelope", default=None
)


@dataclass
class TaskEnvelope:
    goal: str
    from_agent: str = "zaine-core"
    to_agent: str = "zaine-coder"
    parent_request_id: str = "req-0000"
    envelope_id: str = field(default_factory=lambda: f"ENV-{uuid.uuid4().hex[:8].upper()}")
    schema_version: int = 1
    brief: str = ""
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    granted_clusters: List[str] = field(default_factory=list)
    denied_tools: List[str] = field(default_factory=list)
    memory_grants: List[str] = field(default_factory=list)
    max_steps: int = 6
    deadline_s: int = 120
    approval_policy: str = "standard"
    privacy_class: str = "LOCAL_ONLY"
    return_schema: str = "result.v1"

    def __post_init__(self):
        # Validate brief length (<= 600 chars / ~120 tokens)
        if len(self.brief) > 600:
            logger.warning("Truncating TaskEnvelope brief to 600 characters")
            self.brief = self.brief[:597] + "..."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskEnvelope":
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**clean)


@dataclass
class ResultEnvelope:
    envelope_id: str
    status: str = "ok"  # ok, partial, failed, needs_approval, cancelled
    summary: str = ""
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    tool_log: List[Dict[str, Any]] = field(default_factory=list)
    taint: Dict[str, bool] = field(default_factory=lambda: {"untrusted_inputs": False, "private": True})
    usage: Dict[str, int] = field(default_factory=lambda: {"model_calls": 0, "prompt_tokens": 0, "eval_tokens": 0})
    schema_version: int = 1

    def __post_init__(self):
        # Validate summary length (<= 1000 chars / ~200 tokens)
        if len(self.summary) > 1000:
            self.summary = self.summary[:997] + "..."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResultEnvelope":
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**clean)


def is_tool_permitted(tool_name: str, agent_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether the given tool is authorized for execution in the current context.
    Checks:
    1. Active TaskEnvelope denied_tools
    2. Active TaskEnvelope granted_clusters
    3. Default permissions for supervisor agent ('zaine-core' has full access)
    """
    clean_tool = (tool_name or "").strip().lower()
    active_agent = agent_id or current_agent_var.get("zaine-core")
    envelope = current_envelope_var.get(None)

    # Supervisor agent 'zaine-core' has full operational clearance
    if active_agent in ("zaine-core", "jarvis", "supervisor") and envelope is None:
        return True, None

    # If an envelope is active, enforce envelope policy
    if envelope:
        # 1. Deny list check
        normalized_denials = [d.strip().lower() for d in envelope.denied_tools]
        if clean_tool in normalized_denials:
            reason = f"Security Policy: Tool '{tool_name}' is explicitly denied in TaskEnvelope {envelope.envelope_id}"
            logger.warning(reason)
            return False, reason

        # 2. Granted cluster check (if granted_clusters specified)
        if envelope.granted_clusters:
            try:
                import tool_clusters
                cluster_tools = []
                for cl in envelope.granted_clusters:
                    tools_in_cl = tool_clusters.get_tools_for_cluster(cl)
                    cluster_tools.extend([t.lower() for t in tools_in_cl])
                
                # Check if tool belongs to any granted cluster
                if clean_tool not in cluster_tools and clean_tool not in ("final_answer", "clarification"):
                    reason = f"Security Policy: Tool '{tool_name}' is outside granted clusters {envelope.granted_clusters}"
                    logger.warning(reason)
                    return False, reason
            except Exception as e:
                logger.debug("Cluster check fallback: %s", e)

    return True, None

