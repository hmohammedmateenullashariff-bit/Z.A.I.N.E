"""
Z.A.I.N.E — Safe SQLite to Obsidian Vault Memory Migration Tool
Non-destructive, idempotent, read-only extraction of historical memories,
lessons, and conversation episodes from zaine_tasks.db into Obsidian Markdown files.

Usage:
    python migrate_memory_sqlite_to_obsidian.py [--dry-run] [--verbose] [--vault-path <path>]
"""

import os
import sys
import argparse
import sqlite3
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from memory_types import (
    MemoryEntry, MemoryType, MemoryStatus, TrustLevel, MemorySource,
    generate_memory_id
)
from memory_manager import MemoryManager, MemoryPolicy


def categorize_key(key: str) -> Tuple[MemoryType, List[str]]:
    """Determines memory type and tags based on key naming."""
    k_lower = key.lower()
    if any(w in k_lower for w in ["zara", "person", "friend", "colleague", "contact"]):
        return MemoryType.PERSON, ["people", "relationship"]
    elif any(w in k_lower for w in ["favorite", "pref", "like", "drink", "framework", "theme", "setting"]):
        return MemoryType.PREFERENCE, ["preference", "lifestyle" if "drink" in k_lower else "dev"]
    elif any(w in k_lower for w in ["technique", "algorithm", "fibonacci", "architecture", "pattern"]):
        return MemoryType.FACT, ["technical", "knowledge"]
    else:
        return MemoryType.FACT, ["general"]


class MemoryMigrator:
    def __init__(self, db_path: Path, vault_path: Optional[str] = None, dry_run: bool = False, verbose: bool = False):
        self.db_path = db_path
        self.dry_run = dry_run
        self.verbose = verbose
        self.mm = MemoryManager(vault_path=vault_path)
        
        self.stats = {
            "memories_total": 0,
            "memories_migrated": 0,
            "memories_skipped": 0,
            "episodes_total": 0,
            "episodes_migrated": 0,
            "episodes_skipped": 0,
            "learnings_total": 0,
            "learnings_migrated": 0,
            "learnings_skipped": 0,
            "learnings_deduped": 0,
            "errors": 0,
        }

    def _get_existing_source_refs(self) -> Set[str]:
        """Scans the vault to collect existing source_refs to guarantee idempotency."""
        existing_refs = set()
        if not self.mm.available:
            return existing_refs

        all_entries = self.mm.adapter.list_all(limit=5000)
        for e in all_entries:
            if e.source_ref:
                existing_refs.add(e.source_ref)
        return existing_refs

    def run(self):
        print(f"\n{'='*70}")
        print(f" Z.A.I.N.E — SQLite to Obsidian Vault Migration")
        print(f" Source SQLite DB : {self.db_path}")
        print(f" Target Vault     : {self.mm.adapter.vault_path}")
        print(f" Vault Available  : {self.mm.available}")
        print(f" Dry Run Mode     : {self.dry_run}")
        print(f"{'='*70}\n")

        if not self.db_path.exists():
            print(f"[ERROR] Database file not found: {self.db_path}")
            return

        if not self.mm.available and not self.dry_run:
            print(f"[ERROR] Obsidian vault is not available or path is invalid.")
            return

        # Open SQLite in strictly READ-ONLY mode
        uri = f"file:{self.db_path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)

        existing_refs = self._get_existing_source_refs()
        if self.verbose:
            print(f"[Info] Found {len(existing_refs)} existing memory entries in vault.")

        self._migrate_memories(conn, existing_refs)
        self._migrate_episodes(conn, existing_refs)
        self._migrate_learnings(conn, existing_refs)

        conn.close()
        self._print_summary()

    def _migrate_memories(self, conn: sqlite3.Connection, existing_refs: Set[str]):
        """Migrates key-value facts and preferences from 'memories' table."""
        print("--> Migrating 'memories' table (Key-Value Facts & Preferences)...")
        try:
            rows = conn.execute("SELECT key, value, updated_at FROM memories ORDER BY key").fetchall()
        except sqlite3.OperationalError:
            print("    [Notice] 'memories' table not found or empty.")
            return

        self.stats["memories_total"] = len(rows)

        for key, value, updated_at in rows:
            source_ref = f"sqlite_memories_{key}"
            if source_ref in existing_refs:
                self.stats["memories_skipped"] += 1
                if self.verbose:
                    print(f"    [Skip] Already exists: {key}")
                continue

            mem_type, tags = categorize_key(key)
            title = key.replace("_", " ").title()

            entry = MemoryEntry(
                id=generate_memory_id(),
                type=mem_type,
                title=title,
                content=value.strip(),
                status=MemoryStatus.ACTIVE,
                trust=TrustLevel.AUTHORITATIVE,
                source=MemorySource.IMPORT,
                source_ref=source_ref,
                tags=tags + [key.replace("_", "-")],
                created=updated_at[:10] if updated_at else datetime.date.today().isoformat(),
                updated=updated_at[:10] if updated_at else datetime.date.today().isoformat(),
                context=f"Migrated from SQLite table 'memories' (key: {key})",
            )

            is_valid, reason = MemoryPolicy.validate_write(entry)
            if not is_valid:
                print(f"    [Rejected by Policy] {key}: {reason}")
                self.stats["errors"] += 1
                continue

            if not self.dry_run:
                path = self.mm.adapter.write(entry)
                if path:
                    self.stats["memories_migrated"] += 1
                    existing_refs.add(source_ref)
                    if self.verbose:
                        print(f"    [Migrated] {title} -> {path.name}")
                else:
                    self.stats["errors"] += 1
            else:
                self.stats["memories_migrated"] += 1
                if self.verbose:
                    print(f"    [Dry-run] Would migrate: {title}")

    def _migrate_episodes(self, conn: sqlite3.Connection, existing_refs: Set[str]):
        """Migrates conversation_episodes table."""
        print("\n--> Migrating 'conversation_episodes' table (Episodic Session Summaries)...")
        try:
            rows = conn.execute(
                "SELECT id, session_start, session_end, topic_summary, key_points, keywords, created_at "
                "FROM conversation_episodes ORDER BY id ASC"
            ).fetchall()
        except sqlite3.OperationalError:
            print("    [Notice] 'conversation_episodes' table not found or empty.")
            return

        self.stats["episodes_total"] = len(rows)

        for row_id, s_start, s_end, topic_summary, key_points, keywords, created_at in rows:
            source_ref = f"sqlite_episode_{row_id}"
            if source_ref in existing_refs:
                self.stats["episodes_skipped"] += 1
                if self.verbose:
                    print(f"    [Skip] Episode #{row_id} already exists.")
                continue

            title = f"Episode: {topic_summary[:50].strip()}"
            body_content = f"### Summary\n{topic_summary.strip()}"
            if key_points and key_points.strip():
                body_content += f"\n\n### Key Discussion Points\n{key_points.strip()}"

            tag_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else ["conversation"]

            entry = MemoryEntry(
                id=generate_memory_id(),
                type=MemoryType.EPISODE,
                title=title,
                content=body_content,
                status=MemoryStatus.ACTIVE,
                trust=TrustLevel.DERIVED,
                source=MemorySource.CONVERSATION,
                source_ref=source_ref,
                tags=tag_list,
                created=created_at[:10] if created_at else datetime.date.today().isoformat(),
                updated=created_at[:10] if created_at else datetime.date.today().isoformat(),
                context=f"Session from {s_start} to {s_end}",
            )

            is_valid, reason = MemoryPolicy.validate_write(entry)
            if not is_valid:
                print(f"    [Rejected by Policy] Episode #{row_id}: {reason}")
                self.stats["errors"] += 1
                continue

            if not self.dry_run:
                path = self.mm.adapter.write(entry)
                if path:
                    self.stats["episodes_migrated"] += 1
                    existing_refs.add(source_ref)
                    if self.verbose:
                        print(f"    [Migrated] Episode #{row_id} -> {path.name}")
                else:
                    self.stats["errors"] += 1
            else:
                self.stats["episodes_migrated"] += 1
                if self.verbose:
                    print(f"    [Dry-run] Would migrate Episode #{row_id}: {title}")

    def _migrate_learnings(self, conn: sqlite3.Connection, existing_refs: Set[str]):
        """Migrates task_learnings table with deduplication and quality filtering."""
        print("\n--> Migrating 'task_learnings' table (Lessons Learned)...")
        try:
            rows = conn.execute(
                "SELECT id, task_summary, status, lesson_learned, keywords, created_at "
                "FROM task_learnings ORDER BY id ASC"
            ).fetchall()
        except sqlite3.OperationalError:
            print("    [Notice] 'task_learnings' table not found or empty.")
            return

        self.stats["learnings_total"] = len(rows)
        seen_lessons: Set[str] = set()

        # Pre-seed seen_lessons from existing vault notes so duplicate content is never re-migrated
        if self.mm.adapter.vault_path:
            lessons_folder = self.mm.adapter.vault_path / "05_Lessons"
            if lessons_folder.exists():
                for f in lessons_folder.glob("*.md"):
                    if f.name in ("README.md", "Memory-Schema.md", "Memory-Policy.md"):
                        continue
                    entry = self.mm.adapter._parse_file(f)
                    if entry and entry.content:
                        seen_lessons.add(" ".join(entry.content.strip().lower().split()))

        for row_id, task_summary, status, lesson_learned, keywords, created_at in rows:
            source_ref = f"sqlite_task_learning_{row_id}"
            clean_lesson = lesson_learned.strip()
            norm_lesson = " ".join(clean_lesson.lower().split())

            if source_ref in existing_refs:
                self.stats["learnings_skipped"] += 1
                seen_lessons.add(norm_lesson)
                continue

            # Deduplicate similar or identical lesson strings
            if norm_lesson in seen_lessons:
                self.stats["learnings_deduped"] += 1
                continue

            # Quality filter: skip very short or empty lessons
            if len(clean_lesson) < 15 or "none" in norm_lesson[:10]:
                self.stats["learnings_skipped"] += 1
                continue

            seen_lessons.add(norm_lesson)

            title = f"Lesson: {clean_lesson[:50].strip()}"
            tag_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else ["lesson", "autonomous"]

            entry = MemoryEntry(
                id=generate_memory_id(),
                type=MemoryType.LESSON,
                title=title,
                content=clean_lesson,
                status=MemoryStatus.ACTIVE,
                trust=TrustLevel.PROVISIONAL,
                source=MemorySource.AGENT_INFERENCE,
                source_ref=source_ref,
                tags=tag_list,
                created=created_at[:10] if created_at else datetime.date.today().isoformat(),
                updated=created_at[:10] if created_at else datetime.date.today().isoformat(),
                context=f"Autonomous reflection from task: {task_summary}",
                evidence=f"Task execution status: {status}",
            )

            is_valid, reason = MemoryPolicy.validate_write(entry)
            if not is_valid:
                if self.verbose:
                    print(f"    [Skipped by Policy] Lesson #{row_id}: {reason}")
                self.stats["errors"] += 1
                continue

            if not self.dry_run:
                path = self.mm.adapter.write(entry)
                if path:
                    self.stats["learnings_migrated"] += 1
                    existing_refs.add(source_ref)
                    if self.verbose:
                        print(f"    [Migrated] Lesson #{row_id} -> {path.name}")
                else:
                    self.stats["errors"] += 1
            else:
                self.stats["learnings_migrated"] += 1
                if self.verbose:
                    print(f"    [Dry-run] Would migrate Lesson #{row_id}: {title}")

    def _print_summary(self):
        print(f"\n{'='*70}")
        print(" MIGRATION COMPLETE — SUMMARY REPORT")
        print(f"{'='*70}")
        print(f" Key-Value Memories  : {self.stats['memories_total']} total | {self.stats['memories_migrated']} migrated | {self.stats['memories_skipped']} skipped")
        print(f" Episodic Sessions   : {self.stats['episodes_total']} total | {self.stats['episodes_migrated']} migrated | {self.stats['episodes_skipped']} skipped")
        print(f" Task Lessons        : {self.stats['learnings_total']} total | {self.stats['learnings_migrated']} migrated | {self.stats['learnings_deduped']} deduped | {self.stats['learnings_skipped']} skipped")
        print(f" Errors / Rejected   : {self.stats['errors']}")
        print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="Z.A.I.N.E Safe SQLite to Obsidian Vault Memory Migrator")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without writing files")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed migration logs")
    parser.add_argument("--vault-path", type=str, default=None, help="Custom Obsidian vault directory path")
    parser.add_argument("--db-path", type=str, default="zaine_tasks.db", help="Path to source SQLite database")

    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    migrator = MemoryMigrator(
        db_path=db_path,
        vault_path=args.vault_path,
        dry_run=args.dry_run,
        verbose=args.verbose
    )
    migrator.run()


if __name__ == "__main__":
    main()
