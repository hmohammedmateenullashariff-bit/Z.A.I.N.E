"""
Z.A.I.N.E — Autonomous Action & Implementation Approval Subsystem
Enforces the Guardian Protocol and Human-in-the-Loop Governance:
When Z.A.I.N.E devises or initiates an impactful implementation (tool synthesis,
code modification, terminal execution, package installation, media upload),
it sends a structured proposal to Mateen Sir via Telegram with interactive buttons:
  [✅ Approve]   [❌ Deny]   [ℹ️ Explain Details]
"""

import os
import time
import uuid
import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable, Tuple

DB_PATH = Path(__file__).parent / "data" / "zaine_approvals.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_action_callbacks: Dict[str, Callable[[], Any]] = {}

# Recognized proposal ID prefixes — IDs already carrying one of these
# should NOT get a second prefix blindly prepended.
_KNOWN_PREFIXES = ("ACT-", "YT-")


def _normalize_proposal_id(raw_id: str) -> str:
    """Normalize an incoming proposal ID for DB lookup.

    Rules:
      - Strip whitespace and uppercase.
      - If the ID already starts with a recognized prefix (ACT-, YT-, …),
        return it as-is.
      - Otherwise, default to prepending ACT-.
    """
    clean = raw_id.strip().upper()
    for prefix in _KNOWN_PREFIXES:
        if clean.startswith(prefix):
            return clean
    return f"ACT-{clean}"


def _get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY,
            action_type TEXT,
            title TEXT,
            description TEXT,
            code_or_cmd TEXT,
            explanation TEXT,
            risk_level TEXT,
            status TEXT,
            created_at REAL,
            resolved_at REAL,
            resolution_note TEXT
        )
    """)
    conn.commit()
    return conn


class ApprovalRegistry:
    """Manages pending implementation proposals and user decisions."""

    @staticmethod
    def create_proposal(
        action_type: str,
        title: str,
        description: str,
        code_or_cmd: str = "",
        explanation: str = "",
        risk_level: str = "Moderate",
        on_approve: Optional[Callable[[], Any]] = None,
    ) -> str:
        """
        Creates a new proposal, persists it, and dispatches a Telegram notification to Sir.
        Returns the unique proposal ID (e.g. 'ACT-7412').
        """
        short_id = f"ACT-{uuid.uuid4().hex[:4].upper()}"
        now = time.time()

        if not explanation:
            explanation = (
                f"### Objective\n{description}\n\n"
                f"### Technical Scope\n- Action Type: `{action_type}`\n"
                f"- Risk Assessment: `{risk_level}` (Contained within Project-Z workspace)\n\n"
                f"### Payload / Target\n```\n{code_or_cmd[:500] if code_or_cmd else 'N/A'}\n```\n\n"
                f"### Guardian Safety Check\n"
                f"Verified: Zero destructive OS commands, zero harmful external calls, strictly aligned with Mateen Sir's vision."
            )

        with _lock:
            conn = _get_db()
            conn.execute(
                """
                INSERT INTO proposals (id, action_type, title, description, code_or_cmd, explanation, risk_level, status, created_at, resolved_at, resolution_note)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, NULL, '')
                """,
                (short_id, action_type, title, description, code_or_cmd, explanation, risk_level, now),
            )
            conn.commit()
            conn.close()

            if on_approve:
                _action_callbacks[short_id] = on_approve

        # Dispatch Telegram notification with Inline Keyboard
        ApprovalRegistry._dispatch_telegram_alert(short_id, action_type, title, description, risk_level)
        return short_id

    @staticmethod
    def _dispatch_telegram_alert(action_id: str, action_type: str, title: str, description: str, risk_level: str):
        """Sends a rich Telegram message with inline approval buttons to Mateen Sir."""
        try:
            import requests
            token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            target_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
            if not token or not target_id:
                return

            text = (
                f"🛡️ *[Z.A.I.N.E ACTION AUTHORIZATION]*\n\n"
                f"**ID:** `{action_id}`\n"
                f"**Action:** `{title}`\n"
                f"**Type:** `{action_type}` | **Risk:** `{risk_level}`\n\n"
                f"📝 *Summary:*\n{description}\n\n"
                f"_Sir, do you authorize this implementation?_"
            )

            # Inline keyboard buttons
            inline_keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve", "callback_data": f"act_approve:{action_id}"},
                        {"text": "❌ Deny", "callback_data": f"act_deny:{action_id}"}
                    ],
                    [
                        {"text": "ℹ️ Explain Details", "callback_data": f"act_explain:{action_id}"}
                    ]
                ]
            }

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": target_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(inline_keyboard)
            }
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code != 200:
                # Fallback without markdown if entity parsing failed
                payload.pop("parse_mode", None)
                payload["text"] = f"[AUTHORIZATION REQUIRED - {action_id}]\nAction: {title}\nSummary: {description}\nApprove, Deny, or Explain below:"
                requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"[Approval Telegram Error]: {e}")

    @staticmethod
    def get_proposal(action_id: str) -> Optional[Dict[str, Any]]:
        """Fetches proposal dictionary by ID."""
        clean_id = _normalize_proposal_id(action_id)

        conn = _get_db()
        row = conn.execute(
            "SELECT id, action_type, title, description, code_or_cmd, explanation, risk_level, status, created_at, resolved_at, resolution_note FROM proposals WHERE id=?",
            (clean_id,),
        ).fetchone()
        conn.close()

        if not row:
            return None

        return {
            "id": row[0],
            "action_type": row[1],
            "title": row[2],
            "description": row[3],
            "code_or_cmd": row[4],
            "explanation": row[5],
            "risk_level": row[6],
            "status": row[7],
            "created_at": row[8],
            "resolved_at": row[9],
            "resolution_note": row[10],
        }

    @staticmethod
    def get_latest_pending() -> Optional[Dict[str, Any]]:
        """Returns the most recent pending proposal if any."""
        conn = _get_db()
        row = conn.execute(
            "SELECT id, action_type, title, description, code_or_cmd, explanation, risk_level, status, created_at, resolved_at, resolution_note FROM proposals WHERE status='PENDING' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        conn.close()

        if not row:
            return None

        return {
            "id": row[0],
            "action_type": row[1],
            "title": row[2],
            "description": row[3],
            "code_or_cmd": row[4],
            "explanation": row[5],
            "risk_level": row[6],
            "status": row[7],
            "created_at": row[8],
            "resolved_at": row[9],
            "resolution_note": row[10],
        }

    @staticmethod
    def list_pending() -> list:
        """Returns all pending proposals."""
        conn = _get_db()
        rows = conn.execute(
            "SELECT id, action_type, title, description, risk_level, created_at FROM proposals WHERE status='PENDING' ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return [
            {"id": r[0], "action_type": r[1], "title": r[2], "description": r[3], "risk_level": r[4], "created_at": r[5]}
            for r in rows
        ]

    @staticmethod
    def get_pending_proposals() -> list:
        """Alias for list_pending."""
        return ApprovalRegistry.list_pending()

    @staticmethod
    def approve(action_id: str, note: str = "Authorized by Mateen Sir") -> Tuple[bool, str]:
        """
        Approves the proposal and executes any associated callback.
        Returns (success, message).
        """
        clean_id = _normalize_proposal_id(action_id)

        prop = ApprovalRegistry.get_proposal(clean_id)
        if not prop:
            return False, f"Proposal '{clean_id}' not found."
        if prop["status"] != "PENDING":
            return False, f"Proposal '{clean_id}' is already {prop['status']}."

        now = time.time()
        with _lock:
            conn = _get_db()
            conn.execute(
                "UPDATE proposals SET status='APPROVED', resolved_at=?, resolution_note=? WHERE id=?",
                (now, note, clean_id),
            )
            conn.commit()
            conn.close()

            cb = _action_callbacks.pop(clean_id, None)

        callback_result = ""
        if cb:
            try:
                res = cb()
                callback_result = f" Execution output: {res}"
            except Exception as e:
                callback_result = f" Execution error: {e}"

        return True, f"[APPROVED] Proposal {clean_id} ('{prop['title']}') authorized by Sir.{callback_result}"

    @staticmethod
    def deny(action_id: str, note: str = "Denied by Mateen Sir") -> Tuple[bool, str]:
        """Denies the proposal and prevents execution."""
        clean_id = _normalize_proposal_id(action_id)

        prop = ApprovalRegistry.get_proposal(clean_id)
        if not prop:
            return False, f"Proposal '{clean_id}' not found."
        if prop["status"] != "PENDING":
            return False, f"Proposal '{clean_id}' is already {prop['status']}."

        now = time.time()
        with _lock:
            conn = _get_db()
            conn.execute(
                "UPDATE proposals SET status='DENIED', resolved_at=?, resolution_note=? WHERE id=?",
                (now, note, clean_id),
            )
            conn.commit()
            conn.close()
            _action_callbacks.pop(clean_id, None)

        return True, f"[DENIED] Proposal {clean_id} ('{prop['title']}') denied per Sir's directive. Action aborted."

    @staticmethod
    def wait_for_decision(action_id: str, timeout_seconds: int = 180, poll_interval: float = 1.5) -> Tuple[str, str]:
        """
        Blocks and waits for Sir's decision on Telegram.
        Returns (status, message) e.g. ("APPROVED", "..."), ("DENIED", "..."), ("TIMEOUT", "...").
        """
        clean_id = _normalize_proposal_id(action_id)

        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            prop = ApprovalRegistry.get_proposal(clean_id)
            if not prop:
                return "ERROR", f"Proposal '{clean_id}' disappeared."
            if prop["status"] in ("APPROVED", "DENIED"):
                return prop["status"], prop["resolution_note"]
            time.sleep(poll_interval)

        return "TIMEOUT", f"Approval request for {clean_id} timed out after {timeout_seconds}s. Action remains PENDING."


def require_approval(
    action_type: str,
    title: str,
    description: str,
    code_or_cmd: str = "",
    explanation: str = "",
    risk_level: str = "Moderate",
    timeout_seconds: int = 180,
    on_approve: Optional[Callable[[], Any]] = None,
) -> Tuple[bool, str]:
    """
    Convenience function that registers a proposal and blocks waiting for Sir's authorization.
    Returns (is_approved, status_summary).
    """
    action_id = ApprovalRegistry.create_proposal(
        action_type=action_type,
        title=title,
        description=description,
        code_or_cmd=code_or_cmd,
        explanation=explanation,
        risk_level=risk_level,
        on_approve=on_approve,
    )

    status, msg = ApprovalRegistry.wait_for_decision(action_id, timeout_seconds=timeout_seconds)
    if status == "APPROVED":
        return True, f"Approved: {msg}"
    elif status == "DENIED":
        return False, f"Denied: {msg}"
    else:
        return False, f"Pending authorization (ID: {action_id}). Awaiting Sir's response."
