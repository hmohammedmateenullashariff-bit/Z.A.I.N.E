"""
db/learned_rules.py
Hardened failure events and deduplicated learned rules engine for Project-Z (Z.A.I.N.E).
Implements the AI Council consensus specification (Claude Sonnet 5.5 backend critique):
- failure_events: Append-only black box log (never fed to LLMs).
- learned_rules: Deduplicated rules with FTS5 virtual table synchronization.
- Candidates remain inactive until verified deterministically or approved by user via /rules.
- Strict token-bloat guard: get_active_rules_for_prompt limits injection to at most 2 rules or 280 chars.
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from db.engine import get_db_engine

logger = logging.getLogger("zaine.db.learned_rules")


def compute_fingerprint(tool: Optional[str], error_class: str, message: str) -> str:
    """Computes a stable SHA-256 fingerprint for deduplicating errors and rules."""
    norm_tool = (tool or "global").strip().lower()
    norm_err = error_class.strip().lower()
    # Normalize message: strip numbers, hex addresses, line numbers, and transient timestamps
    norm_msg = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", message)
    norm_msg = re.sub(r"\d+", "NUM", norm_msg).strip().lower()
    raw = f"{norm_tool}|{norm_err}|{norm_msg}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def init_hardened_schema() -> bool:
    """
    Initializes failure_events, learned_rules, and FTS5 synchronization triggers.
    Safely migrates legacy task_learnings records into candidate rules without altering
    the legacy table.
    """
    engine = get_db_engine()

    ddl_script = """
    CREATE TABLE IF NOT EXISTS failure_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts_utc TEXT NOT NULL,
        request_id TEXT,
        run_id TEXT,
        agent_id TEXT NOT NULL DEFAULT 'zaine-core',
        tool TEXT,
        error_class TEXT NOT NULL,
        retryable INTEGER NOT NULL CHECK (retryable IN (0,1)),
        fingerprint TEXT NOT NULL,
        message_redacted TEXT NOT NULL CHECK (length(message_redacted) <= 400),
        breaker_before TEXT,
        breaker_after TEXT,
        duration_ms INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_fe_fp_ts ON failure_events(fingerprint, ts_utc);

    CREATE TABLE IF NOT EXISTS learned_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fingerprint TEXT NOT NULL UNIQUE,
        scope TEXT NOT NULL CHECK (scope IN ('tool','agent','global')),
        trigger_tool TEXT,
        trigger_error_class TEXT,
        rule_text TEXT NOT NULL CHECK (length(rule_text) <= 140),
        source TEXT NOT NULL CHECK (source IN ('deterministic','llm_proposed','user')),
        trust TEXT NOT NULL CHECK (trust IN ('AUTHORITATIVE','VERIFIED','DERIVED','PROVISIONAL','UNTRUSTED')),
        status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','active','retired','rejected')),
        hit_count INTEGER NOT NULL DEFAULT 1,
        applied_count INTEGER NOT NULL DEFAULT 0,
        helped_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        expires_at TEXT
    );
    """
    ok, err = engine.execute_script(ddl_script)
    if not ok:
        logger.error("Failed to create base tables: %s", err)
        return False

    # Check FTS5 table
    fts_script = """
    CREATE VIRTUAL TABLE IF NOT EXISTS learned_rules_fts USING fts5(
        rule_text,
        trigger_tool,
        content='learned_rules',
        content_rowid='id'
    );

    CREATE TRIGGER IF NOT EXISTS lr_ai AFTER INSERT ON learned_rules BEGIN
        INSERT INTO learned_rules_fts(rowid, rule_text, trigger_tool)
        VALUES (new.id, new.rule_text, new.trigger_tool);
    END;

    CREATE TRIGGER IF NOT EXISTS lr_ad AFTER DELETE ON learned_rules BEGIN
        INSERT INTO learned_rules_fts(learned_rules_fts, rowid, rule_text, trigger_tool)
        VALUES ('delete', old.id, old.rule_text, old.trigger_tool);
    END;

    CREATE TRIGGER IF NOT EXISTS lr_au AFTER UPDATE ON learned_rules BEGIN
        INSERT INTO learned_rules_fts(learned_rules_fts, rowid, rule_text, trigger_tool)
        VALUES ('delete', old.id, old.rule_text, old.trigger_tool);
        INSERT INTO learned_rules_fts(rowid, rule_text, trigger_tool)
        VALUES (new.id, new.rule_text, new.trigger_tool);
    END;
    """
    ok_fts, err_fts = engine.execute_script(fts_script)
    if not ok_fts:
        logger.warning("FTS5 table/triggers creation notice: %s", err_fts)

    # Migrate legacy task_learnings if table exists and has rows
    _migrate_legacy_learnings()
    return True


def _migrate_legacy_learnings() -> None:
    """Migrates distinct legacy task_learnings into learned_rules as DERIVED candidates."""
    engine = get_db_engine()
    rows = engine.execute_read("SELECT name FROM sqlite_master WHERE type='table' AND name='task_learnings';")
    if not rows:
        return

    # Count existing in learned_rules
    res = engine.execute_read("SELECT count(*) FROM learned_rules;")
    if res and res[0][0] > 0:
        return  # already migrated

    try:
        legacy_rows = engine.execute_read("""
            SELECT task_summary, status, lesson_learned, keywords, created_at 
            FROM task_learnings 
            ORDER BY id ASC;
        """)
        logger.info("Migrating %d legacy task_learnings rows into learned_rules...", len(legacy_rows))
        now_iso = datetime.now(timezone.utc).isoformat()

        migrated = 0
        for row in legacy_rows:
            task_summary, status_val, lesson_learned, keywords, created_at = row
            rule_content = lesson_learned
            if not rule_content or len(rule_content.strip()) < 5:
                continue
            rule_text = rule_content.strip()[:140]
            fp = hashlib.sha256(f"legacy|{keywords or task_summary}|{rule_text}".encode("utf-8")).hexdigest()[:32]

            sql = """
            INSERT INTO learned_rules (
                fingerprint, scope, trigger_tool, trigger_error_class,
                rule_text, source, trust, status, hit_count, created_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(fingerprint) DO UPDATE SET 
                hit_count = hit_count + 1,
                last_seen_at = excluded.last_seen_at;
            """
            ok, _, _ = engine.execute_write(
                sql,
                (fp, "tool", (keywords or task_summary or "general")[:50], "failure_pattern" if status_val == "failed" else "general",
                 rule_text, "deterministic", "DERIVED", "candidate", created_at or now_iso, now_iso)
            )
            if ok:
                migrated += 1
        logger.info("Successfully migrated %d distinct rules into learned_rules", migrated)
    except Exception as e:
        logger.error("Error migrating legacy learnings: %s", e)


def record_failure_event(
    error_class: str,
    message: str,
    tool: Optional[str] = None,
    agent_id: str = "zaine-core",
    request_id: Optional[str] = None,
    run_id: Optional[str] = None,
    retryable: bool = False,
    breaker_before: Optional[str] = None,
    breaker_after: Optional[str] = None,
    duration_ms: Optional[int] = None
) -> Tuple[bool, str]:
    """
    Records an immutable failure incident into failure_events blackbox table.
    Zero LLM calls. Fully synchronous, fast, and deterministic.
    Returns: (success: bool, fingerprint: str)
    """
    engine = get_db_engine()
    now_utc = datetime.now(timezone.utc).isoformat()
    fp = compute_fingerprint(tool, error_class, message)
    redacted_msg = (message or "").strip()[:400]

    sql = """
    INSERT INTO failure_events (
        ts_utc, request_id, run_id, agent_id, tool, error_class,
        retryable, fingerprint, message_redacted, breaker_before, breaker_after, duration_ms
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    params = (
        now_utc, request_id, run_id, agent_id, tool, error_class,
        1 if retryable else 0, fp, redacted_msg, breaker_before, breaker_after, duration_ms
    )
    ok, _, _ = engine.execute_write(sql, params)
    return ok, fp


def upsert_candidate_rule(
    rule_text: str,
    scope: str = "tool",
    trigger_tool: Optional[str] = None,
    trigger_error_class: Optional[str] = None,
    source: str = "deterministic",
    trust: str = "VERIFIED",
    auto_activate: bool = False
) -> Tuple[bool, str]:
    """
    Upserts a candidate rule into learned_rules.
    If already exists, increments hit_count and updates last_seen_at.
    Only deterministic and user rules may auto-activate; llm_proposed remains candidate.
    """
    engine = get_db_engine()
    clean_rule = rule_text.strip()[:140]
    fp = compute_fingerprint(trigger_tool, trigger_error_class or "any", clean_rule)
    now_utc = datetime.now(timezone.utc).isoformat()

    status = "active" if (auto_activate and source in ("deterministic", "user")) else "candidate"

    sql = """
    INSERT INTO learned_rules (
        fingerprint, scope, trigger_tool, trigger_error_class,
        rule_text, source, trust, status, hit_count, created_at, last_seen_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
    ON CONFLICT(fingerprint) DO UPDATE SET 
        hit_count = hit_count + 1,
        last_seen_at = excluded.last_seen_at;
    """
    params = (
        fp, scope, trigger_tool, trigger_error_class,
        clean_rule, source, trust, status, now_utc, now_utc
    )
    ok, _, _ = engine.execute_write(sql, params)
    return ok, fp


def get_active_rules_for_prompt(
    tool_name: Optional[str] = None,
    error_class: Optional[str] = None,
    limit: int = 2
) -> List[str]:
    """
    Retrieves active learned rules matching tool or error class.
    Enforces strict token bloat limits: at most 2 rules or 280 characters total.
    """
    engine = get_db_engine()
    results = []

    # First attempt: exact match by tool
    if tool_name:
        sql = """
        SELECT rule_text FROM learned_rules 
        WHERE status = 'active' AND (trigger_tool = ? OR scope = 'global')
        ORDER BY hit_count DESC, last_seen_at DESC LIMIT ?;
        """
        rows = engine.execute_read(sql, (tool_name, limit))
        for r in rows:
            results.append(r[0])

    # If limit not reached, fallback to FTS5 query if tool or error_class provided
    if len(results) < limit and (tool_name or error_class):
        search_query = f"{tool_name or ''} {error_class or ''}".strip()
        if search_query:
            try:
                fts_sql = """
                SELECT r.rule_text FROM learned_rules_fts f
                JOIN learned_rules r ON r.id = f.rowid
                WHERE f.learned_rules_fts MATCH ? AND r.status = 'active'
                ORDER BY r.hit_count DESC LIMIT ?;
                """
                fts_rows = engine.execute_read(fts_sql, (search_query, limit - len(results)))
                for fr in fts_rows:
                    if fr[0] not in results:
                        results.append(fr[0])
            except Exception:
                pass

    # Cap total characters at 280
    bounded = []
    total_chars = 0
    for rule in results[:limit]:
        if total_chars + len(rule) <= 280:
            bounded.append(rule)
            total_chars += len(rule)
    return bounded


def list_candidate_rules(limit: int = 20) -> List[Dict[str, Any]]:
    """Returns candidate rules pending user inspection and approval."""
    engine = get_db_engine()
    sql = """
    SELECT id, fingerprint, scope, trigger_tool, trigger_error_class, 
           rule_text, source, trust, hit_count, created_at, last_seen_at 
    FROM learned_rules 
    WHERE status = 'candidate' 
    ORDER BY hit_count DESC, last_seen_at DESC LIMIT ?;
    """
    rows = engine.execute_read(sql, (limit,))
    candidates = []
    for r in rows:
        candidates.append({
            "id": r[0],
            "fingerprint": r[1],
            "scope": r[2],
            "trigger_tool": r[3],
            "trigger_error_class": r[4],
            "rule_text": r[5],
            "source": r[6],
            "trust": r[7],
            "hit_count": r[8],
            "created_at": r[9],
            "last_seen_at": r[10]
        })
    return candidates


def approve_candidate_rule(rule_id: int) -> bool:
    """Promotes a candidate rule to active status upon user approval."""
    engine = get_db_engine()
    sql = "UPDATE learned_rules SET status = 'active', trust = 'VERIFIED' WHERE id = ? AND status = 'candidate';"
    ok, _, _ = engine.execute_write(sql, (rule_id,))
    return ok
