"""
Z.A.I.N.E — Memory Type Definitions & Data Structures
Defines the canonical memory entry schema aligned with Memory-Schema.md.
These dataclasses provide a structured, type-safe representation of durable memories
with full provenance, trust, and lifecycle metadata.
"""

import uuid
import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from enum import Enum


class MemoryType(str, Enum):
    """Memory classification types aligned with Memory-Schema.md Section 2."""
    FACT = "fact"
    PREFERENCE = "preference"
    PERSON = "person"
    PROJECT = "project"
    EPISODE = "episode"
    LESSON = "lesson"
    DECISION = "decision"
    REFERENCE = "reference"
    SYSTEM = "system"


class MemoryStatus(str, Enum):
    """Memory lifecycle states aligned with Memory-Schema.md Section 3."""
    ACTIVE = "active"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class TrustLevel(str, Enum):
    """Trust classification aligned with Memory-Schema.md Section 3.
    Ordered from highest to lowest trust.
    """
    AUTHORITATIVE = "authoritative"
    VERIFIED = "verified"
    DERIVED = "derived"
    PROVISIONAL = "provisional"
    UNTRUSTED = "untrusted"
    REJECTED = "rejected"


class MemorySource(str, Enum):
    """Provenance classification aligned with Memory-Schema.md Section 3."""
    USER = "user"
    CONVERSATION = "conversation"
    TOOL = "tool"
    WEB = "web"
    AGENT_INFERENCE = "agent_inference"
    SYSTEM = "system"
    IMPORT = "import"


def generate_memory_id() -> str:
    """Generates a deterministic, unique memory ID."""
    short_uuid = uuid.uuid4().hex[:12]
    return f"mem_{short_uuid}"


@dataclass
class MemoryEntry:
    """
    Canonical memory entry aligned with Memory-Schema.md.
    Every field maps directly to a YAML frontmatter key in the Obsidian vault.
    """
    # Required fields
    id: str = field(default_factory=generate_memory_id)
    type: MemoryType = MemoryType.FACT
    title: str = ""
    content: str = ""

    # Lifecycle
    status: MemoryStatus = MemoryStatus.ACTIVE
    trust: TrustLevel = TrustLevel.PROVISIONAL
    source: MemorySource = MemorySource.CONVERSATION

    # Timestamps
    created: str = field(default_factory=lambda: datetime.date.today().isoformat())
    updated: str = field(default_factory=lambda: datetime.date.today().isoformat())

    # Optional provenance
    source_ref: Optional[str] = None
    last_confirmed: Optional[str] = None
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None

    # Classification
    tags: List[str] = field(default_factory=list)
    related: List[str] = field(default_factory=list)

    # Additional context sections (stored in Markdown body)
    context: str = ""
    evidence: str = ""
    notes: str = ""

    def to_frontmatter_dict(self) -> dict:
        """Converts to a dict suitable for YAML frontmatter serialization.
        Omits None/empty optional fields for clean Markdown output.
        """
        d = {
            "id": self.id,
            "type": self.type.value if isinstance(self.type, MemoryType) else self.type,
            "title": self.title,
            "status": self.status.value if isinstance(self.status, MemoryStatus) else self.status,
            "trust": self.trust.value if isinstance(self.trust, TrustLevel) else self.trust,
            "source": self.source.value if isinstance(self.source, MemorySource) else self.source,
            "created": self.created,
            "updated": self.updated,
        }
        # Optional fields — only include if set
        if self.source_ref:
            d["source_ref"] = self.source_ref
        if self.last_confirmed:
            d["last_confirmed"] = self.last_confirmed
        if self.supersedes:
            d["supersedes"] = self.supersedes
        if self.superseded_by:
            d["superseded_by"] = self.superseded_by
        if self.tags:
            d["tags"] = self.tags
        if self.related:
            d["related"] = self.related
        return d

    def to_markdown(self) -> str:
        """Renders a complete Markdown file with YAML frontmatter and body content."""
        import yaml
        fm = self.to_frontmatter_dict()
        # Use block style for readability
        yaml_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()
        lines = [f"---\n{yaml_str}\n---\n"]
        lines.append(f"# {self.title}\n")
        if self.content:
            lines.append(f"{self.content}\n")
        if self.context:
            lines.append(f"## Context\n\n{self.context}\n")
        if self.evidence:
            lines.append(f"## Evidence\n\n{self.evidence}\n")
        if self.notes:
            lines.append(f"## Notes\n\n{self.notes}\n")
        return "\n".join(lines)

    @classmethod
    def from_frontmatter(cls, frontmatter: dict, body: str = "") -> "MemoryEntry":
        """Reconstructs a MemoryEntry from parsed YAML frontmatter and Markdown body."""
        # Parse enums safely
        mem_type = frontmatter.get("type", "fact")
        try:
            mem_type = MemoryType(mem_type)
        except ValueError:
            mem_type = MemoryType.FACT

        mem_status = frontmatter.get("status", "active")
        try:
            mem_status = MemoryStatus(mem_status)
        except ValueError:
            mem_status = MemoryStatus.ACTIVE

        trust = frontmatter.get("trust", "provisional")
        try:
            trust = TrustLevel(trust)
        except ValueError:
            trust = TrustLevel.PROVISIONAL

        source = frontmatter.get("source", "conversation")
        try:
            source = MemorySource(source)
        except ValueError:
            source = MemorySource.CONVERSATION

        # Parse body sections
        content = ""
        context = ""
        evidence = ""
        notes = ""
        if body:
            # Split on ## headers
            import re
            # Remove the title heading
            body_clean = re.sub(r"^#\s+.*?\n", "", body, count=1).strip()
            parts = re.split(r"^##\s+", body_clean, flags=re.MULTILINE)
            if parts:
                content = parts[0].strip()
            for part in parts[1:]:
                if part.lower().startswith("context"):
                    context = part.split("\n", 1)[1].strip() if "\n" in part else ""
                elif part.lower().startswith("evidence"):
                    evidence = part.split("\n", 1)[1].strip() if "\n" in part else ""
                elif part.lower().startswith("notes"):
                    notes = part.split("\n", 1)[1].strip() if "\n" in part else ""

        return cls(
            id=frontmatter.get("id", generate_memory_id()),
            type=mem_type,
            title=frontmatter.get("title", ""),
            content=content,
            status=mem_status,
            trust=trust,
            source=source,
            created=str(frontmatter.get("created", datetime.date.today().isoformat())),
            updated=str(frontmatter.get("updated", datetime.date.today().isoformat())),
            source_ref=frontmatter.get("source_ref"),
            last_confirmed=frontmatter.get("last_confirmed"),
            supersedes=frontmatter.get("supersedes"),
            superseded_by=frontmatter.get("superseded_by"),
            tags=frontmatter.get("tags", []) or [],
            related=frontmatter.get("related", []) or [],
            context=context,
            evidence=evidence,
            notes=notes,
        )

    def is_retrievable(self) -> bool:
        """Returns True if this memory should appear in active retrieval.
        Per Memory-Policy.md: rejected memories must never be retrieved.
        Archived memories are excluded from normal retrieval.
        """
        return self.status == MemoryStatus.ACTIVE

    def is_trusted(self) -> bool:
        """Returns True if this memory has at least 'derived' trust level."""
        trusted_levels = {TrustLevel.AUTHORITATIVE, TrustLevel.VERIFIED, TrustLevel.DERIVED}
        return self.trust in trusted_levels

    def format_for_context(self, include_trust: bool = True) -> str:
        """Formats this memory for injection into the LLM context window.
        Per Memory-Policy.md Section 15: retrieved memory must retain trust metadata.
        """
        trust_tag = f" [{self.trust.value}]" if include_trust else ""
        type_tag = f"[{self.type.value}]"
        return f"- {type_tag}{trust_tag} {self.title}: {self.content}"
