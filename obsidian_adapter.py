"""
Z.A.I.N.E — Obsidian Vault Storage Adapter
Provides controlled, safe read/write access to the Obsidian vault for durable memory storage.

Design principles (from Memory-Schema.md & Memory-Policy.md):
- Vault path is configurable (NEVER hardcoded)
- Markdown-based storage with YAML frontmatter
- Deterministic file naming from memory IDs
- Safe writes (write-then-rename for atomicity)
- UTF-8 encoding
- No accidental vault-wide rewrites
- No deletion during migration
- Adapter is replaceable
"""

import os
import re
import tempfile
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from memory_types import (
    MemoryEntry, MemoryType, MemoryStatus, TrustLevel, MemorySource,
    generate_memory_id
)


# Directory mapping: MemoryType → Obsidian folder
TYPE_TO_FOLDER: Dict[MemoryType, str] = {
    MemoryType.FACT: "03_Preferences",
    MemoryType.PREFERENCE: "03_Preferences",
    MemoryType.PERSON: "01_People",
    MemoryType.PROJECT: "02_Projects",
    MemoryType.EPISODE: "04_Episodes",
    MemoryType.LESSON: "05_Lessons",
    MemoryType.DECISION: "06_Decisions",
    MemoryType.REFERENCE: "07_Reference",
    MemoryType.SYSTEM: "00_System",
}


def _sanitize_filename(text: str, max_length: int = 60) -> str:
    """Creates a safe filename from arbitrary text.
    Removes special characters, replaces spaces with hyphens, truncates.
    """
    # Remove characters unsafe for Windows/Unix filenames
    clean = re.sub(r'[\\/*?:"<>|]', '', text)
    # Replace whitespace runs with single hyphen
    clean = re.sub(r'\s+', '-', clean.strip())
    # Remove any remaining problematic characters
    clean = re.sub(r'[^\w\-.]', '', clean)
    # Truncate
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip('-')
    return clean or "untitled"


class ObsidianAdapter:
    """
    Controlled storage adapter for reading/writing memory entries
    to an Obsidian vault as Markdown files with YAML frontmatter.
    
    The adapter does not depend on Obsidian being running or installed.
    It only interacts with the filesystem representation of the vault.
    """

    def __init__(self, vault_path: Optional[str] = None):
        """Initialize with configurable vault path.
        
        Args:
            vault_path: Absolute path to the Obsidian vault root.
                        If None, reads from ZAINE_OBSIDIAN_VAULT_PATH env var.
                        Falls back to a disabled state if neither is set.
        """
        self._vault_path: Optional[Path] = None
        self._available = False

        resolved = vault_path or os.environ.get("ZAINE_OBSIDIAN_VAULT_PATH", "")
        if resolved:
            p = Path(resolved)
            if p.exists() and p.is_dir():
                self._vault_path = p
                self._available = True
            else:
                # Path configured but doesn't exist — log warning but don't crash
                print(f"[ObsidianAdapter] Warning: vault path '{resolved}' does not exist. Memory adapter disabled.")

    @property
    def available(self) -> bool:
        """Returns True if the vault is accessible and ready for operations."""
        return self._available and self._vault_path is not None

    @property
    def vault_path(self) -> Optional[Path]:
        return self._vault_path

    def _get_folder(self, mem_type: MemoryType) -> Path:
        """Returns the vault subfolder for a given memory type."""
        folder_name = TYPE_TO_FOLDER.get(mem_type, "07_Reference")
        folder = self._vault_path / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _get_filepath(self, entry: MemoryEntry) -> Path:
        """Deterministic filepath for a memory entry based on type and ID."""
        folder = self._get_folder(entry.type)
        # Use ID as the primary filename component for determinism
        safe_title = _sanitize_filename(entry.title) if entry.title else "untitled"
        filename = f"{entry.id}_{safe_title}.md"
        return folder / filename

    def _find_by_id(self, memory_id: str) -> Optional[Path]:
        """Finds an existing memory file by its ID prefix."""
        if not self.available:
            return None
        for folder_name in TYPE_TO_FOLDER.values():
            folder = self._vault_path / folder_name
            if folder.exists():
                for f in folder.glob(f"{memory_id}_*.md"):
                    return f
        # Also check archive
        archive = self._vault_path / "99_Archive"
        if archive.exists():
            for f in archive.glob(f"{memory_id}_*.md"):
                return f
        return None

    def write(self, entry: MemoryEntry) -> Optional[Path]:
        """Writes a memory entry to the vault as a Markdown file.
        
        Uses write-then-rename for safe atomic writes on Windows.
        Returns the final file path on success, None on failure.
        """
        if not self.available:
            return None

        filepath = self._get_filepath(entry)
        markdown = entry.to_markdown()

        try:
            # Ensure parent directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write: write to temp file in same directory, then rename
            fd, tmp_path = tempfile.mkstemp(
                suffix=".md.tmp",
                dir=str(filepath.parent)
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(markdown)
                # On Windows, we need to remove the target first if it exists
                if filepath.exists():
                    filepath.unlink()
                Path(tmp_path).rename(filepath)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            return filepath
        except Exception as e:
            print(f"[ObsidianAdapter] Error writing {entry.id}: {e}")
            return None

    def read(self, memory_id: str) -> Optional[MemoryEntry]:
        """Reads a memory entry from the vault by its ID.
        
        Parses YAML frontmatter and Markdown body.
        Returns None if not found or on parse error.
        """
        if not self.available:
            return None

        filepath = self._find_by_id(memory_id)
        if not filepath or not filepath.exists():
            return None

        try:
            return self._parse_file(filepath)
        except Exception as e:
            print(f"[ObsidianAdapter] Error reading {memory_id}: {e}")
            return None

    def _parse_file(self, filepath: Path) -> Optional[MemoryEntry]:
        """Parses a Markdown file with YAML frontmatter into a MemoryEntry."""
        try:
            import yaml
        except ImportError:
            print("[ObsidianAdapter] PyYAML not installed. Cannot parse frontmatter.")
            return None

        try:
            text = filepath.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            print(f"[ObsidianAdapter] Error reading file {filepath}: {e}")
            return None

        # Parse frontmatter
        if not text.startswith("---"):
            return None

        parts = text.split("---", 2)
        if len(parts) < 3:
            return None

        try:
            frontmatter = yaml.safe_load(parts[1])
        except Exception:
            return None

        if not isinstance(frontmatter, dict):
            return None

        body = parts[2].strip()
        return MemoryEntry.from_frontmatter(frontmatter, body)

    def search(
        self,
        query: str = "",
        mem_type: Optional[MemoryType] = None,
        status: MemoryStatus = MemoryStatus.ACTIVE,
        trust_min: Optional[TrustLevel] = None,
        limit: int = 10,
        tags: Optional[List[str]] = None,
    ) -> List[MemoryEntry]:
        """Searches the vault for matching memories.
        
        Current implementation: lexical scan with keyword matching.
        Future: could be upgraded to FTS5, BM25, or vector search.
        
        Args:
            query: Search keywords (space-separated, case-insensitive)
            mem_type: Filter by memory type
            status: Filter by status (default: active only)
            trust_min: Minimum trust level to include
            limit: Maximum results to return
            tags: Filter by tag intersection
            
        Returns:
            List of matching MemoryEntry objects, sorted by relevance (recency).
        """
        if not self.available:
            return []

        results: List[MemoryEntry] = []
        query_lower = query.lower().strip()
        query_words = set(query_lower.split()) if query_lower else set()

        # Trust ordering for filtering
        trust_order = [
            TrustLevel.REJECTED, TrustLevel.UNTRUSTED, TrustLevel.PROVISIONAL,
            TrustLevel.DERIVED, TrustLevel.VERIFIED, TrustLevel.AUTHORITATIVE
        ]

        # Determine which folders to scan
        if mem_type:
            folders = [TYPE_TO_FOLDER.get(mem_type, "07_Reference")]
        else:
            folders = list(set(TYPE_TO_FOLDER.values()))

        for folder_name in folders:
            folder = self._vault_path / folder_name
            if not folder.exists():
                continue
            for md_file in folder.glob("*.md"):
                entry = self._parse_file(md_file)
                if entry is None:
                    continue

                # Status filter
                if entry.status != status:
                    continue

                # Trust minimum filter
                if trust_min:
                    entry_trust_idx = trust_order.index(entry.trust) if entry.trust in trust_order else 0
                    min_trust_idx = trust_order.index(trust_min)
                    if entry_trust_idx < min_trust_idx:
                        continue

                # Tag filter
                if tags:
                    entry_tags = set(t.lower() for t in entry.tags)
                    if not set(t.lower() for t in tags).intersection(entry_tags):
                        continue

                # Query matching (if query provided)
                if query_words:
                    searchable = f"{entry.title} {entry.content} {' '.join(entry.tags)}".lower()
                    # Require at least one query word to match
                    if not any(w in searchable for w in query_words):
                        continue

                results.append(entry)

                if len(results) >= limit * 3:  # Over-fetch for ranking
                    break

        # Sort by recency (newest first)
        results.sort(key=lambda e: e.updated or e.created, reverse=True)

        return results[:limit]

    def list_all(
        self,
        mem_type: Optional[MemoryType] = None,
        status: Optional[MemoryStatus] = None,
        limit: int = 50
    ) -> List[MemoryEntry]:
        """Lists all memories, optionally filtered by type and status."""
        if not self.available:
            return []

        results: List[MemoryEntry] = []

        if mem_type:
            folders = [TYPE_TO_FOLDER.get(mem_type, "07_Reference")]
        else:
            folders = list(set(TYPE_TO_FOLDER.values()))

        for folder_name in folders:
            folder = self._vault_path / folder_name
            if not folder.exists():
                continue
            for md_file in folder.glob("*.md"):
                # Skip system files that aren't memories
                if md_file.name in ("README.md", "Memory-Schema.md", "Memory-Policy.md"):
                    continue
                entry = self._parse_file(md_file)
                if entry is None:
                    continue
                if status and entry.status != status:
                    continue
                results.append(entry)
                if len(results) >= limit:
                    break

        results.sort(key=lambda e: e.updated or e.created, reverse=True)
        return results[:limit]

    def archive(self, memory_id: str) -> bool:
        """Moves a memory to archived status.
        Updates the status in the file's frontmatter.
        Does NOT delete the file.
        """
        if not self.available:
            return False

        entry = self.read(memory_id)
        if entry is None:
            return False

        # Update status
        old_filepath = self._find_by_id(memory_id)
        entry.status = MemoryStatus.ARCHIVED
        entry.updated = datetime.date.today().isoformat()

        # Move to archive folder
        archive_dir = self._vault_path / "99_Archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Write to archive location
        safe_title = _sanitize_filename(entry.title) if entry.title else "untitled"
        new_filepath = archive_dir / f"{entry.id}_{safe_title}.md"

        try:
            markdown = entry.to_markdown()
            new_filepath.write_text(markdown, encoding='utf-8')
            # Remove from original location (safe because we just wrote the archived copy)
            if old_filepath and old_filepath.exists() and old_filepath != new_filepath:
                old_filepath.unlink()
            return True
        except Exception as e:
            print(f"[ObsidianAdapter] Error archiving {memory_id}: {e}")
            return False

    def reject(self, memory_id: str) -> bool:
        """Marks a memory as rejected.
        Rejected memories are kept for audit but excluded from retrieval.
        """
        if not self.available:
            return False

        entry = self.read(memory_id)
        if entry is None:
            return False

        entry.status = MemoryStatus.REJECTED
        entry.trust = TrustLevel.REJECTED
        entry.updated = datetime.date.today().isoformat()

        # Rewrite in place
        result = self.write(entry)
        return result is not None

    def delete(self, memory_id: str) -> bool:
        """Permanently deletes a memory file.
        Per Memory-Policy.md: only allowed on explicit user request.
        """
        if not self.available:
            return False

        filepath = self._find_by_id(memory_id)
        if filepath and filepath.exists():
            try:
                filepath.unlink()
                return True
            except Exception as e:
                print(f"[ObsidianAdapter] Error deleting {memory_id}: {e}")
                return False
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Returns vault statistics for diagnostics."""
        if not self.available:
            return {"available": False}

        stats = {"available": True, "vault_path": str(self._vault_path), "folders": {}}
        for mem_type, folder_name in TYPE_TO_FOLDER.items():
            folder = self._vault_path / folder_name
            if folder.exists():
                md_count = len(list(folder.glob("*.md")))
                stats["folders"][folder_name] = md_count
            else:
                stats["folders"][folder_name] = 0

        # Archive
        archive = self._vault_path / "99_Archive"
        if archive.exists():
            stats["folders"]["99_Archive"] = len(list(archive.glob("*.md")))

        return stats
