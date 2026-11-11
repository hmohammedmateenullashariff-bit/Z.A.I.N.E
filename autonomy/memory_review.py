"""
autonomy/memory_review.py
Memory fact review queue preventing autonomous trust promotion (Constraint #5).

Invariants:
- Reuses db.engine.DatabaseEngine (WAL-mode SQLite single-writer queue).
- Autonomous inference/tool/web/conversation observations NEVER promote memory trust.
- Repeated facts are routed exclusively into `memory_review_queue` (status='pending_review')
  with an incrementing repeat_count until explicitly approved or rejected by an operator.
"""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from memory_types import MemoryEntry, MemorySource, MemoryStatus, MemoryType, PrivacyTaint, TrustLevel

_SCHEMA_LOCK = threading.Lock()
_INITIALIZED_DBS: set[str] = set()

_DDL = """
CREATE TABLE IF NOT EXISTS memory_review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    mem_type TEXT NOT NULL DEFAULT 'fact',
    source TEXT NOT NULL DEFAULT 'agent_inference',
    proposed_trust TEXT NOT NULL DEFAULT 'provisional',
    privacy_taint TEXT NOT NULL DEFAULT 'LOCAL_ONLY',
    repeat_count INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (status IN ('pending_review', 'approved', 'rejected')),
    existing_memory_id TEXT,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_mrq_status_seen
    ON memory_review_queue(status, repeat_count DESC, last_seen_at DESC);
"""


def _resolve_engine(engine: Optional[Any] = None):
    if engine is not None:
        return engine
    from db.engine import get_db_engine

    return get_db_engine()


def init_memory_review_schema(engine: Optional[Any] = None) -> bool:
    """Idempotently creates the memory_review_queue table using the WAL DB engine."""
    eng = _resolve_engine(engine)
    db_key = str(getattr(eng, "db_path", id(eng)))
    with _SCHEMA_LOCK:
        if db_key in _INITIALIZED_DBS:
            return True
        ok, _err = eng.execute_script(_DDL)
        if ok:
            _INITIALIZED_DBS.add(db_key)
        return ok


def compute_fact_fingerprint(title: str, content: str, mem_type: str = "fact") -> str:
    """Deterministic fingerprint for deduplicating repeated fact assertions."""
    norm_type = str(mem_type or "fact").strip().lower()
    norm_title = " ".join(str(title or "").strip().lower().split())
    norm_content = " ".join(str(content or "").strip().lower().split())
    raw = f"{norm_type}|{norm_title}|{norm_content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _clamp_autonomous_trust(source: str, requested_trust: Optional[str]) -> str:
    src = str(source or "agent_inference").strip().lower()
    if src in (MemorySource.WEB.value, MemorySource.TOOL.value):
        return TrustLevel.UNTRUSTED.value
    req = str(requested_trust or TrustLevel.PROVISIONAL.value).strip().lower()
    if req in (TrustLevel.REJECTED.value, TrustLevel.UNTRUSTED.value, TrustLevel.PROVISIONAL.value):
        return req
    # Never allow autonomous non-user submission to claim DERIVED/VERIFIED/AUTHORITATIVE
    return TrustLevel.PROVISIONAL.value


def submit_fact_candidate(
    title: str,
    content: str,
    *,
    mem_type: str = MemoryType.FACT.value,
    source: str = MemorySource.AGENT_INFERENCE.value,
    trust: Optional[str] = None,
    privacy_taint: str = PrivacyTaint.LOCAL_ONLY.value,
    existing_memory_id: Optional[str] = None,
    engine: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Queues a candidate or repeated fact in `memory_review_queue` with ZERO autonomous
    trust promotion. Increments `repeat_count` when seen repeatedly.
    """
    clean_title = str(title or "").strip()
    clean_content = str(content or "").strip()
    if not clean_title or not clean_content:
        return {"queued": False, "error": "Title and content cannot be empty.", "trust_promoted": False}

    try:
        from memory_manager import MemoryPolicy

        safe, reason = MemoryPolicy.check_safe_text(f"{clean_title} {clean_content}")
        if not safe:
            return {"queued": False, "error": f"Blocked by MemoryPolicy: {reason}", "trust_promoted": False}
    except Exception:
        pass

    eng = _resolve_engine(engine)
    init_memory_review_schema(eng)

    norm_type = mem_type.value if isinstance(mem_type, MemoryType) else str(mem_type or "fact").strip().lower()
    norm_src = source.value if isinstance(source, MemorySource) else str(source or "agent_inference").strip().lower()
    clamped_trust = _clamp_autonomous_trust(norm_src, trust.value if isinstance(trust, TrustLevel) else trust)
    norm_taint = (
        PrivacyTaint.SHAREABLE.value
        if str(privacy_taint or "").strip().upper() == PrivacyTaint.SHAREABLE.value
        else PrivacyTaint.LOCAL_ONLY.value
    )

    fp = compute_fact_fingerprint(clean_title, clean_content, norm_type)
    now_utc = datetime.now(timezone.utc).isoformat()

    sql = """
    INSERT INTO memory_review_queue (
        fingerprint, title, content, mem_type, source, proposed_trust,
        privacy_taint, repeat_count, status, existing_memory_id, created_at, last_seen_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'pending_review', ?, ?, ?)
    ON CONFLICT(fingerprint) DO UPDATE SET
        repeat_count = repeat_count + 1,
        last_seen_at = excluded.last_seen_at,
        existing_memory_id = COALESCE(memory_review_queue.existing_memory_id, excluded.existing_memory_id);
    """
    ok, _rowid, err = eng.execute_write(
        sql,
        (
            fp,
            clean_title[:240],
            clean_content[:2000],
            norm_type,
            norm_src,
            clamped_trust,
            norm_taint,
            existing_memory_id,
            now_utc,
            now_utc,
        ),
    )
    if not ok:
        return {"queued": False, "error": err or "DB write failed", "trust_promoted": False}

    rows = eng.execute_read(
        "SELECT id, repeat_count, status, proposed_trust, privacy_taint FROM memory_review_queue WHERE fingerprint = ?;",
        (fp,),
    )
    if rows:
        row = rows[0]
        return {
            "queued": True,
            "id": row[0],
            "fingerprint": fp,
            "repeat_count": row[1],
            "status": row[2],
            "trust": row[3],
            "privacy_taint": row[4],
            "trust_promoted": False,
        }
    return {"queued": True, "fingerprint": fp, "repeat_count": 1, "status": "pending_review", "trust_promoted": False}


def list_review_queue(
    status: Optional[str] = "pending_review",
    limit: int = 50,
    engine: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Lists fact review queue items without modifying trust levels."""
    eng = _resolve_engine(engine)
    init_memory_review_schema(eng)
    if status:
        rows = eng.execute_read(
            """
            SELECT id, fingerprint, title, content, mem_type, source, proposed_trust,
                   privacy_taint, repeat_count, status, existing_memory_id, created_at, last_seen_at, reviewed_at
            FROM memory_review_queue
            WHERE status = ?
            ORDER BY repeat_count DESC, last_seen_at DESC
            LIMIT ?;
            """,
            (status, int(limit)),
        )
    else:
        rows = eng.execute_read(
            """
            SELECT id, fingerprint, title, content, mem_type, source, proposed_trust,
                   privacy_taint, repeat_count, status, existing_memory_id, created_at, last_seen_at, reviewed_at
            FROM memory_review_queue
            ORDER BY repeat_count DESC, last_seen_at DESC
            LIMIT ?;
            """,
            (int(limit),),
        )
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "fingerprint": r[1],
                "title": r[2],
                "content": r[3],
                "mem_type": r[4],
                "source": r[5],
                "proposed_trust": r[6],
                "privacy_taint": r[7],
                "repeat_count": r[8],
                "status": r[9],
                "existing_memory_id": r[10],
                "created_at": r[11],
                "last_seen_at": r[12],
                "reviewed_at": r[13],
            }
        )
    return out


def approve_review_item(
    candidate_id: int,
    *,
    promote_to: TrustLevel = TrustLevel.VERIFIED,
    write_to_vault: bool = True,
    memory_manager: Optional[Any] = None,
    engine: Optional[Any] = None,
) -> Tuple[bool, str]:
    """
    Explicit operator approval path: promotes a queued candidate fact ONLY when an
    operator explicitly invokes approval.
    """
    eng = _resolve_engine(engine)
    init_memory_review_schema(eng)
    rows = eng.execute_read(
        """
        SELECT id, title, content, mem_type, source, privacy_taint, existing_memory_id, status
        FROM memory_review_queue WHERE id = ?;
        """,
        (int(candidate_id),),
    )
    if not rows:
        return False, f"Review item {candidate_id} not found."
    row = rows[0]
    _id, title, content, mem_type_str, src_str, priv_taint, existing_id, cur_status = row
    if cur_status == "rejected":
        return False, f"Review item {candidate_id} was previously rejected."

    target_trust = promote_to if isinstance(promote_to, TrustLevel) else TrustLevel(str(promote_to))
    now_utc = datetime.now(timezone.utc).isoformat()
    ok, _rid, err = eng.execute_write(
        "UPDATE memory_review_queue SET status = 'approved', proposed_trust = ?, reviewed_at = ? WHERE id = ?;",
        (target_trust.value, now_utc, int(candidate_id)),
    )
    if not ok:
        return False, err or "Failed to update review item."

    if write_to_vault:
        mm = memory_manager
        if mm is None:
            from memory_manager import get_memory_manager

            mm = get_memory_manager()
        if mm is not None and mm.available:
            if existing_id:
                existing_entry = mm.adapter.read(existing_id)
                if existing_entry is not None:
                    mm.update(existing_id, trust=target_trust, user_approved=True)
                    return True, f"Promoted existing memory {existing_id} to trust={target_trust.value}."
            try:
                mt = MemoryType(mem_type_str)
            except ValueError:
                mt = MemoryType.FACT
            mm.create(
                title=title,
                content=content,
                mem_type=mt,
                source=MemorySource.USER,
                trust=target_trust,
                privacy_taint=priv_taint,
                notes=f"Operator approved candidate #{candidate_id} (origin source: {src_str}).",
            )
    return True, f"Approved review item {candidate_id} at trust={target_trust.value}."


def reject_review_item(candidate_id: int, *, engine: Optional[Any] = None) -> Tuple[bool, str]:
    """Marks a queued candidate fact as rejected."""
    eng = _resolve_engine(engine)
    init_memory_review_schema(eng)
    now_utc = datetime.now(timezone.utc).isoformat()
    ok, _rid, err = eng.execute_write(
        "UPDATE memory_review_queue SET status = 'rejected', reviewed_at = ? WHERE id = ?;",
        (now_utc, int(candidate_id)),
    )
    if not ok:
        return False, err or f"Failed to reject review item {candidate_id}."
    return True, f"Rejected review item {candidate_id}."


def _find_matching_vault_entry(mm: Any, title: str, content: str) -> Optional[MemoryEntry]:
    if mm is None or not getattr(mm, "available", False):
        return None
    norm_title = " ".join(title.strip().lower().split())
    norm_content = " ".join(content.strip().lower().split())
    try:
        matches = mm.adapter.search(query=title, status=MemoryStatus.ACTIVE, limit=10)
    except Exception:
        return None
    for entry in matches:
        et = " ".join((entry.title or "").strip().lower().split())
        ec = " ".join((entry.content or "").strip().lower().split())
        if et == norm_title and (ec == norm_content or norm_content in ec or ec in norm_content):
            return entry
        if et == norm_title and norm_title:
            return entry
    return None


def record_agent_fact(
    title: str,
    content: str,
    *,
    mem_type: MemoryType = MemoryType.FACT,
    source: MemorySource = MemorySource.AGENT_INFERENCE,
    privacy_taint: str = PrivacyTaint.LOCAL_ONLY.value,
    tags: Optional[List[str]] = None,
    memory_manager: Optional[Any] = None,
    engine: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Records an autonomous/inferred fact while enforcing Constraint #5:
    - Never promotes trust automatically.
    - If a matching fact already exists in Obsidian vault or review queue, sends the
      repeated assertion ONLY to `memory_review_queue` and leaves existing trust unchanged.
    """
    clean_title = str(title or "").strip()
    clean_content = str(content or "").strip()
    if not clean_title or not clean_content:
        return {"status": "error", "error": "Title and content cannot be empty.", "trust_promoted": False}

    mm = memory_manager
    if mm is None:
        from memory_manager import get_memory_manager

        mm = get_memory_manager()

    existing = _find_matching_vault_entry(mm, clean_title, clean_content)
    if existing is not None:
        q = submit_fact_candidate(
            clean_title,
            clean_content,
            mem_type=mem_type.value if isinstance(mem_type, MemoryType) else str(mem_type),
            source=source.value if isinstance(source, MemorySource) else str(source),
            trust=existing.trust.value,
            privacy_taint=privacy_taint,
            existing_memory_id=existing.id,
            engine=engine,
        )
        return {
            "status": "queued_for_review",
            "queued_for_review": True,
            "existing_memory_id": existing.id,
            "existing_trust": existing.trust.value,
            "trust_promoted": False,
            **q,
        }

    # If no vault match yet, also check if already present in queue or store initial provisional item
    eng = _resolve_engine(engine)
    init_memory_review_schema(eng)
    fp = compute_fact_fingerprint(
        clean_title,
        clean_content,
        mem_type.value if isinstance(mem_type, MemoryType) else str(mem_type),
    )
    already_queued = eng.execute_read("SELECT id FROM memory_review_queue WHERE fingerprint = ?;", (fp,))
    if already_queued:
        q = submit_fact_candidate(
            clean_title,
            clean_content,
            mem_type=mem_type.value if isinstance(mem_type, MemoryType) else str(mem_type),
            source=source.value if isinstance(source, MemorySource) else str(source),
            privacy_taint=privacy_taint,
            engine=engine,
        )
        return {"status": "queued_for_review", "queued_for_review": True, "trust_promoted": False, **q}

    if mm is not None and getattr(mm, "available", False):
        trust_lvl = (
            TrustLevel.UNTRUSTED
            if source in (MemorySource.WEB, MemorySource.TOOL)
            else TrustLevel.PROVISIONAL
        )
        entry, msg = mm.create(
            title=clean_title,
            content=clean_content,
            mem_type=mem_type,
            source=source,
            trust=trust_lvl,
            tags=tags or [],
            privacy_taint=privacy_taint,
        )
        if entry is None:
            return {"status": "rejected", "error": msg, "trust_promoted": False}
        return {
            "status": "stored_provisional",
            "queued_for_review": False,
            "memory_id": entry.id,
            "trust": entry.trust.value,
            "privacy_taint": entry.privacy_taint,
            "trust_promoted": False,
        }

    # Vault unavailable -> still queue safely for review, never auto-promote
    q = submit_fact_candidate(
        clean_title,
        clean_content,
        mem_type=mem_type.value if isinstance(mem_type, MemoryType) else str(mem_type),
        source=source.value if isinstance(source, MemorySource) else str(source),
        privacy_taint=privacy_taint,
        engine=engine,
    )
    return {"status": "queued_for_review", "queued_for_review": True, "trust_promoted": False, **q}

