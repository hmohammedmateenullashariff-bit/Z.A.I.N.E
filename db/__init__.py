"""
db/
Database management and hardened SQLite persistence engine for Project-Z (Z.A.I.N.E).
Enforces WAL mode, busy_timeout=5000, serialized single-writer queue with JSONL blackbox fallback,
and FTS5-indexed learned rules.
"""

from db.engine import get_db_engine, DatabaseEngine
from db.learned_rules import (
    record_failure_event,
    upsert_candidate_rule,
    get_active_rules_for_prompt,
    list_candidate_rules,
    approve_candidate_rule,
    init_hardened_schema
)

__all__ = [
    "get_db_engine",
    "DatabaseEngine",
    "record_failure_event",
    "upsert_candidate_rule",
    "get_active_rules_for_prompt",
    "list_candidate_rules",
    "approve_candidate_rule",
    "init_hardened_schema"
]

