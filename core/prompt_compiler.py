"""
core/prompt_compiler.py
Prefix-Cache-Aware Prompt Compiler for Zero-Latency KV-Cache Reuse.

Exploits Ollama/llama.cpp exact prefix KV-cache matching:
If the first N tokens of the system prompt are byte-for-byte identical across turns,
the inference engine skips prompt evaluation (reducing TTFT from ~1.46s down to <0.05s).

Structure:
- STATIC_PREFIX (Slot 0): Immutable Persona Identity + Security Policies + Tool Calling JSON Schema.
- DYNAMIC_TAIL (Slot 1+): Operator Clock + Retrieved FTS5 Rules + Conversation Turns.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CompiledPrompt:
    agent_id: str
    static_prefix: str
    static_hash: str
    messages: List[Dict[str, str]]
    cached_prefix_tokens: int


class PromptCompiler:
    # Immutable System Core Templates (Byte-stable per persona)
    BASE_STATIC_TEMPLATE = (
        "You are Z.A.I.N.E (Zero-latency Autonomous Intelligent Neural Entity), an advanced personal AI.\n"
        "Active Persona: {agent_name} [{agent_id}]. Clearance: {clearance}.\n"
        "Operating Environment: Windows 11 Home, Local Sovereign Station, RTX 2050 4GB VRAM.\n\n"
        "OPERATIONAL DIRECTIVES:\n"
        "1. Prioritize speed, precision, and privacy. Never leak private keys or operator data.\n"
        "2. Do not hallucinate capabilities. If a task requires an unpermitted tool, report denial.\n"
        "3. Output format must strictly follow designated JSON tool invocation or natural language response.\n\n"
        "TOOL INVOCATION CONTRACT:\n"
        "To invoke a tool, output a single JSON object in this exact schema:\n"
        "{{\"tool\": \"<tool_name>\", \"args\": {{<arguments>}}}}\n"
        "Wait for system tool response before proceeding.\n\n"
        "SECURITY CHOKE POINT:\n"
        "All filesystem writes and commands are gated behind TaskEnvelope verification.\n"
        "Zone 0 Kernel files are immutable. Destructive operations require explicit operator approval."
    )

    def __init__(self):
        self._cache_registry: Dict[str, str] = {}
        self._hash_registry: Dict[str, str] = {}

    def get_static_prefix(self, agent_id: str, agent_name: str, clearance: str) -> Tuple[str, str]:
        """Returns the cached byte-identical static prefix and its SHA-256 fingerprint."""
        cache_key = f"{agent_id}:{agent_name}:{clearance}"
        if cache_key in self._cache_registry:
            return self._cache_registry[cache_key], self._hash_registry[cache_key]

        prefix = self.BASE_STATIC_TEMPLATE.format(
            agent_name=agent_name,
            agent_id=agent_id,
            clearance=clearance,
        ).strip()

        prefix_hash = hashlib.sha256(prefix.encode("utf-8")).hexdigest()
        self._cache_registry[cache_key] = prefix
        self._hash_registry[cache_key] = prefix_hash
        return prefix, prefix_hash

    def compile(
        self,
        agent_id: str,
        agent_name: str,
        clearance: str,
        history: List[Dict[str, str]],
        dynamic_context: Optional[Dict[str, Any]] = None,
        learned_rules: Optional[List[str]] = None,
    ) -> CompiledPrompt:
        """
        Compiles the full message array.
        Slot 0 is guaranteed to be byte-identical to preserve Ollama's KV-cache prefix.
        Dynamic facts, clock, and memory rules are appended strictly in dynamic messages.
        """
        static_prefix, prefix_hash = self.get_static_prefix(agent_id, agent_name, clearance)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": static_prefix}
        ]

        # Slot 1: Dynamic Session Meta (Context & Rules injected as system or contextual user frame)
        meta_sections = []
        if dynamic_context:
            clock = dynamic_context.get("timestamp_iso") or ""
            status = dynamic_context.get("system_status") or "HEALTHY"
            meta_sections.append(f"[WORKSTATION CONTEXT: {clock} | SYSTEM: {status}]")

        if learned_rules:
            rules_str = "\n".join(f"- {r}" for r in learned_rules[:5])
            meta_sections.append(f"[ACTIVE LEARNED RULES (Reflexion Memory)]:\n{rules_str}")

        if meta_sections:
            messages.append({"role": "system", "content": "\n\n".join(meta_sections)})

        # Subsequent slots: Conversation History
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            messages.append({"role": role, "content": content})

        # Estimate prefix tokens (standard ~4 chars per token rule-of-thumb)
        cached_tokens = len(static_prefix) // 4

        return CompiledPrompt(
            agent_id=agent_id,
            static_prefix=static_prefix,
            static_hash=prefix_hash,
            messages=messages,
            cached_prefix_tokens=cached_tokens,
        )


# Global singleton
prompt_compiler = PromptCompiler()
