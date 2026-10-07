"""
Z.A.I.N.E — Memory Manager (Central Memory Orchestrator)
Sits between Z.A.I.N.E's agent and the storage layer, enforcing Memory-Policy.md.

Architecture:
    Z.A.I.N.E Agent
        │
        ▼
    MemoryManager (this module)
        │
        ├── Memory Policy Enforcement
        ├── Trust & Provenance Tracking
        ├── Context Budget Management
        ├── Retrieval with Trust-Aware Ranking
        │
        ├── ObsidianAdapter (durable human-readable storage)
        └── Legacy SQLite Bridge (backward compatibility with memory.py)

All memory operations route through this boundary.
No other module should directly open() or write() to the Obsidian vault.
"""

import os
import re
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from memory_types import (
    MemoryEntry, MemoryType, MemoryStatus, TrustLevel, MemorySource,
    generate_memory_id
)
from obsidian_adapter import ObsidianAdapter


# Context budget defaults (conservative for RTX 2050 / 3B models)
DEFAULT_MAX_MEMORIES = 8
DEFAULT_MAX_CHARS = 2000
DEFAULT_MAX_LESSONS = 3
DEFAULT_MAX_EPISODES = 2


class MemoryPolicy:
    """
    Enforces Memory-Policy.md rules.
    This is the security boundary between Z.A.I.N.E and durable memory.
    """

    # Sources that are NEVER allowed to create authoritative memory automatically
    UNTRUSTED_SOURCES = {MemorySource.WEB, MemorySource.TOOL}

    # Maximum trust level that untrusted sources can achieve without promotion
    MAX_UNTRUSTED_TRUST = TrustLevel.UNTRUSTED

    # Patterns that indicate possible prompt injection in memory content
    INJECTION_PATTERNS = [
        r"(?i)\bsystem\s*(?:override|instruction|directive|prompt)\b",
        r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior|above)\b",
        r"(?i)\bforget\s+(?:all|everything)\b",
        r"(?i)\byou\s+(?:are|must|should)\s+(?:now|always)\b",
        r"(?i)\bnew\s+(?:system|base)\s+(?:prompt|instruction)\b",
    ]

    @classmethod
    def validate_write(
        cls,
        entry: MemoryEntry,
        require_user_request: bool = False
    ) -> Tuple[bool, str]:
        """Validates a memory write against policy rules.
        
        Returns (is_valid, reason).
        """
        # Rule: Empty content is not a memory
        if not entry.title.strip() and not entry.content.strip():
            return False, "Memory title and content cannot both be empty"

        # Rule: Title must be non-empty
        if not entry.title.strip():
            return False, "Memory title cannot be empty"

        # Rule: Untrusted sources cannot create authoritative memories
        if entry.source in cls.UNTRUSTED_SOURCES:
            if entry.trust in {TrustLevel.AUTHORITATIVE, TrustLevel.VERIFIED}:
                return False, (
                    f"Source '{entry.source.value}' cannot create "
                    f"'{entry.trust.value}' memory. Max trust: {cls.MAX_UNTRUSTED_TRUST.value}"
                )
            # Enforce maximum trust ceiling for untrusted sources
            entry.trust = min_trust(entry.trust, cls.MAX_UNTRUSTED_TRUST)

        # Rule: Check for prompt injection patterns
        combined_text = f"{entry.title} {entry.content} {entry.context} {entry.notes}"
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, combined_text):
                return False, f"Potential prompt injection detected: pattern '{pattern}' matched"

        # Rule: Rejected entries should not be resurrected without explicit action
        if entry.status == MemoryStatus.REJECTED and entry.trust != TrustLevel.REJECTED:
            return False, "Rejected memories cannot be resurrected without explicit trust reassignment"

        return True, "OK"

    @classmethod
    def validate_retrieval(cls, entry: MemoryEntry) -> bool:
        """Validates whether a memory should be included in retrieval results.
        Per Memory-Policy.md: rejected memories must never be retrieved.
        """
        if entry.status == MemoryStatus.REJECTED:
            return False
        if entry.trust == TrustLevel.REJECTED:
            return False
        return True

    @classmethod
    def assign_trust_for_source(cls, source: MemorySource) -> TrustLevel:
        """Assigns the appropriate default trust level for a given source.
        Per Memory-Policy.md Section 25: conservative initial behavior.
        """
        trust_map = {
            MemorySource.USER: TrustLevel.AUTHORITATIVE,
            MemorySource.CONVERSATION: TrustLevel.DERIVED,
            MemorySource.SYSTEM: TrustLevel.VERIFIED,
            MemorySource.IMPORT: TrustLevel.PROVISIONAL,
            MemorySource.AGENT_INFERENCE: TrustLevel.PROVISIONAL,
            MemorySource.TOOL: TrustLevel.UNTRUSTED,
            MemorySource.WEB: TrustLevel.UNTRUSTED,
        }
        return trust_map.get(source, TrustLevel.PROVISIONAL)


def min_trust(a: TrustLevel, b: TrustLevel) -> TrustLevel:
    """Returns the lower of two trust levels."""
    order = [
        TrustLevel.REJECTED, TrustLevel.UNTRUSTED, TrustLevel.PROVISIONAL,
        TrustLevel.DERIVED, TrustLevel.VERIFIED, TrustLevel.AUTHORITATIVE
    ]
    idx_a = order.index(a) if a in order else 0
    idx_b = order.index(b) if b in order else 0
    return order[min(idx_a, idx_b)]


class MemoryManager:
    """
    Central memory orchestrator for Z.A.I.N.E.
    All memory operations (create, read, search, archive, reject, delete) go through this class.
    
    Architecture goals:
    - Enforce Memory-Policy.md rules on every write
    - Provide trust-aware retrieval with context budgets
    - Bridge legacy SQLite memory.py with new Obsidian storage
    - Keep backward compatibility for existing agent flow
    """

    def __init__(self, vault_path: Optional[str] = None):
        """Initialize the MemoryManager.
        
        Args:
            vault_path: Path to Obsidian vault. If None, reads from env var
                        ZAINE_OBSIDIAN_VAULT_PATH.
        """
        self.adapter = ObsidianAdapter(vault_path=vault_path)
        self.policy = MemoryPolicy()

        # Context budget settings
        self.max_memories = int(os.environ.get("ZAINE_MAX_MEMORIES", DEFAULT_MAX_MEMORIES))
        self.max_chars = int(os.environ.get("ZAINE_MAX_MEMORY_CHARS", DEFAULT_MAX_CHARS))
        self.max_lessons = DEFAULT_MAX_LESSONS
        self.max_episodes = DEFAULT_MAX_EPISODES

    @property
    def available(self) -> bool:
        """Returns True if the Obsidian vault is accessible."""
        return self.adapter.available

    # ──────────────────────────────────────────────────────────────────────
    # WRITE OPERATIONS
    # ──────────────────────────────────────────────────────────────────────

    def create(
        self,
        title: str,
        content: str,
        mem_type: MemoryType = MemoryType.FACT,
        source: MemorySource = MemorySource.CONVERSATION,
        trust: Optional[TrustLevel] = None,
        tags: Optional[List[str]] = None,
        source_ref: Optional[str] = None,
        context: str = "",
        evidence: str = "",
        notes: str = "",
        related: Optional[List[str]] = None,
    ) -> Tuple[Optional[MemoryEntry], str]:
        """Creates a new memory entry after policy validation.
        
        Returns (entry, message). Entry is None if validation fails.
        """
        # Assign default trust based on source if not explicitly provided
        if trust is None:
            trust = self.policy.assign_trust_for_source(source)

        entry = MemoryEntry(
            id=generate_memory_id(),
            type=mem_type,
            title=title.strip(),
            content=content.strip(),
            source=source,
            trust=trust,
            tags=tags or [],
            source_ref=source_ref,
            context=context,
            evidence=evidence,
            notes=notes,
            related=related or [],
        )

        # Policy validation
        is_valid, reason = self.policy.validate_write(entry)
        if not is_valid:
            return None, f"Memory write rejected: {reason}"

        # Write to Obsidian
        filepath = self.adapter.write(entry)
        if filepath:
            return entry, f"Memory created: {entry.id} → {filepath.name}"
        else:
            return None, "Memory write failed: Obsidian adapter returned None"

    def create_candidate(
        self,
        title: str,
        content: str,
        mem_type: MemoryType = MemoryType.FACT,
        source: MemorySource = MemorySource.AGENT_INFERENCE,
        tags: Optional[List[str]] = None,
        source_ref: Optional[str] = None,
    ) -> Tuple[Optional[MemoryEntry], str]:
        """Creates a candidate/provisional memory.
        Per Memory-Policy.md Section 25: strongly useful inferred information
        becomes candidate/provisional memory.
        """
        return self.create(
            title=title,
            content=content,
            mem_type=mem_type,
            source=source,
            trust=TrustLevel.PROVISIONAL,
            tags=tags,
            source_ref=source_ref,
        )

    def update(
        self,
        memory_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        trust: Optional[TrustLevel] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> Tuple[Optional[MemoryEntry], str]:
        """Updates an existing memory entry.
        Per Memory-Schema.md Section 8: prefer creating a new memory and
        superseding the old one, but simple updates are allowed for minor changes.
        """
        entry = self.adapter.read(memory_id)
        if entry is None:
            return None, f"Memory {memory_id} not found"

        if title is not None:
            entry.title = title.strip()
        if content is not None:
            entry.content = content.strip()
        if trust is not None:
            entry.trust = trust
        if tags is not None:
            entry.tags = tags
        if notes is not None:
            entry.notes = notes

        entry.updated = datetime.date.today().isoformat()

        # Policy validation
        is_valid, reason = self.policy.validate_write(entry)
        if not is_valid:
            return None, f"Memory update rejected: {reason}"

        filepath = self.adapter.write(entry)
        if filepath:
            return entry, f"Memory updated: {memory_id}"
        return None, "Memory update failed"

    def supersede(
        self,
        old_memory_id: str,
        new_title: str,
        new_content: str,
        source: MemorySource = MemorySource.USER,
    ) -> Tuple[Optional[MemoryEntry], str]:
        """Creates a new memory that supersedes an old one.
        Per Memory-Schema.md Section 8: prefer supersession over silent overwrite.
        """
        old_entry = self.adapter.read(old_memory_id)
        if old_entry is None:
            return None, f"Original memory {old_memory_id} not found"

        # Create new entry
        new_entry, msg = self.create(
            title=new_title,
            content=new_content,
            mem_type=old_entry.type,
            source=source,
            trust=self.policy.assign_trust_for_source(source),
            tags=old_entry.tags,
            related=[old_memory_id],
        )

        if new_entry is None:
            return None, msg

        # Mark old entry as superseded
        old_entry.status = MemoryStatus.SUPERSEDED
        old_entry.superseded_by = new_entry.id
        old_entry.updated = datetime.date.today().isoformat()
        self.adapter.write(old_entry)

        # Set supersedes on new entry
        new_entry.supersedes = old_memory_id
        self.adapter.write(new_entry)

        return new_entry, f"Memory {old_memory_id} superseded by {new_entry.id}"

    # ──────────────────────────────────────────────────────────────────────
    # READ & SEARCH OPERATIONS
    # ──────────────────────────────────────────────────────────────────────

    def retrieve(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieves a single memory by ID with policy validation."""
        entry = self.adapter.read(memory_id)
        if entry and not self.policy.validate_retrieval(entry):
            return None
        return entry

    def search(
        self,
        query: str,
        mem_type: Optional[MemoryType] = None,
        limit: int = None,
        tags: Optional[List[str]] = None,
    ) -> List[MemoryEntry]:
        """Searches memories with policy-enforced filtering.
        Never returns rejected or untrusted memories as facts.
        """
        if limit is None:
            limit = self.max_memories

        results = self.adapter.search(
            query=query,
            mem_type=mem_type,
            status=MemoryStatus.ACTIVE,
            limit=limit,
            tags=tags,
        )

        # Policy filter
        return [r for r in results if self.policy.validate_retrieval(r)]

    # ──────────────────────────────────────────────────────────────────────
    # LIFECYCLE OPERATIONS
    # ──────────────────────────────────────────────────────────────────────

    def archive(self, memory_id: str) -> Tuple[bool, str]:
        """Archives a memory (removes from active retrieval, keeps for audit)."""
        success = self.adapter.archive(memory_id)
        if success:
            return True, f"Memory {memory_id} archived"
        return False, f"Failed to archive {memory_id}"

    def reject(self, memory_id: str) -> Tuple[bool, str]:
        """Rejects a memory (marks as invalid, excluded from retrieval)."""
        success = self.adapter.reject(memory_id)
        if success:
            return True, f"Memory {memory_id} rejected"
        return False, f"Failed to reject {memory_id}"

    def delete(self, memory_id: str) -> Tuple[bool, str]:
        """Permanently deletes a memory.
        Per Memory-Policy.md Section 18: only on explicit user request.
        """
        success = self.adapter.delete(memory_id)
        if success:
            return True, f"Memory {memory_id} permanently deleted"
        return False, f"Failed to delete {memory_id}"

    # ──────────────────────────────────────────────────────────────────────
    # CONTEXT CONSTRUCTION (replaces parts of memory.py:get_persistent_context)
    # ──────────────────────────────────────────────────────────────────────

    def build_memory_context(
        self,
        current_prompt: str = "",
        include_legacy: bool = True,
    ) -> str:
        """Builds the memory context block for LLM injection.
        
        This method produces a bounded, trust-annotated memory block
        that replaces the unbounded MEMORY CONTEXT injection.
        
        Architecture:
        1. User profile from Obsidian (or legacy user_profile.md)
        2. Relevant memories from Obsidian vault (bounded by context budget)
        3. Legacy memories from SQLite (backward compatibility)
        
        Returns a formatted string bounded by XML-like tags for safety.
        """
        sections = []
        total_chars = 0

        # ── Section 1: Obsidian vault memories ──
        if self.available and current_prompt:
            vault_memories = self.search(query=current_prompt, limit=self.max_memories)
            if vault_memories:
                mem_lines = []
                for mem in vault_memories:
                    if total_chars >= self.max_chars:
                        break
                    formatted = mem.format_for_context(include_trust=True)
                    total_chars += len(formatted)
                    mem_lines.append(formatted)
                if mem_lines:
                    sections.append(
                        "<retrieved_memory>\n"
                        "Relevant memories from vault:\n" +
                        "\n".join(mem_lines) +
                        "\n</retrieved_memory>"
                    )

        # ── Section 2: Legacy SQLite memories (backward compatibility) ──
        if include_legacy:
            legacy_context = self._get_legacy_context(current_prompt)
            if legacy_context:
                remaining = self.max_chars - total_chars
                if remaining > 200:
                    truncated = legacy_context[:remaining]
                    sections.append(
                        "<legacy_memory>\n" +
                        truncated +
                        "\n</legacy_memory>"
                    )

        if not sections:
            return ""

        return "\n\n".join(sections)

    def _get_legacy_context(self, current_prompt: str = "") -> str:
        """Reads from the existing memory.py SQLite system for backward compatibility.
        This bridges the old system until migration is complete.
        """
        try:
            from memory import get_all_memories, retrieve_relevant_learnings
        except ImportError:
            return ""

        parts = []

        # User profile
        profile_path = Path(__file__).parent / "vault" / "user_profile.md"
        if profile_path.exists():
            try:
                prof = profile_path.read_text(encoding="utf-8", errors="ignore").strip()
                if prof:
                    parts.append(f"User Profile:\n{prof}")
            except Exception:
                pass

        # Known facts (bounded)
        try:
            mems = get_all_memories()
            if mems:
                # Apply budget: max 15 facts
                items = list(mems.items())[:15]
                lines = ["Known facts:"]
                for k, v in items:
                    lines.append(f"- {k}: {v}")
                parts.append("\n".join(lines))
        except Exception:
            pass

        # Relevant lessons (already limited to 3)
        if current_prompt:
            try:
                learnings = retrieve_relevant_learnings(current_prompt, limit=self.max_lessons)
                if learnings:
                    l_lines = ["Relevant past lessons:"]
                    for l in learnings:
                        l_lines.append(f"- {l}")
                    parts.append("\n".join(l_lines))
            except Exception:
                pass

        return "\n\n".join(parts)

    # ──────────────────────────────────────────────────────────────────────
    # DIAGNOSTICS
    # ──────────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Returns combined statistics for diagnostics."""
        stats = {
            "obsidian": self.adapter.get_stats(),
            "context_budget": {
                "max_memories": self.max_memories,
                "max_chars": self.max_chars,
                "max_lessons": self.max_lessons,
                "max_episodes": self.max_episodes,
            },
        }
        return stats


# ──────────────────────────────────────────────────────────────────────────
# Module-level singleton (lazy initialization)
# ──────────────────────────────────────────────────────────────────────────

_manager_instance: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Returns the global MemoryManager singleton.
    Lazy initialization ensures the vault path is read at first use.
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = MemoryManager()
    return _manager_instance
