"""
agents
VisionQuest sub-agents: data-defined profiles (agents/profiles.json) that share the one resident model.
A profile changes the role prompt, the tools offered to the model and the tools it may execute.
"""

from agents.registry import (
    AgentProfile,
    AgentSelection,
    get_registry,
    select_agent,
    parse_mention,
)

__all__ = ["AgentProfile", "AgentSelection", "get_registry", "select_agent", "parse_mention"]
