"""
db/sessions.py
Session-Based Persistence & Thread History Storage for Z.A.I.N.E.

Implements Fix D from ZAINE_RECOVERY_PLAN.md:
Transitions from ephemeral self.history = [] to persisted SQLite session threads.
Enables instant chat history retrieval in HUD and TUI, and thread-isolated context.
Uses SQLite WAL mode via db/engine.py.
"""

import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional
from db.engine import DatabaseEngine


def init_sessions_schema(engine: DatabaseEngine):
    """Initializes chat_sessions and chat_messages tables."""
    engine.execute_script("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        agent_id TEXT NOT NULL DEFAULT 'jarvis',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        model TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_chat_msg_session ON chat_messages(session_id, id);
    """)


class SessionManager:
    def __init__(self):
        self.engine = DatabaseEngine.get_instance()
        init_sessions_schema(self.engine)

    def create_session(
        self,
        session_id: Optional[str] = None,
        title: str = "New Conversation",
        agent_id: str = "jarvis"
    ) -> str:
        sid = session_id or f"ses-{uuid.uuid4().hex[:8]}"
        self.engine.execute_write(
            "INSERT INTO chat_sessions (id, title, agent_id) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at=CURRENT_TIMESTAMP;",
            (sid, title, agent_id),
        )
        return sid

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self.engine.execute_read(
            "SELECT id, title, agent_id, created_at, updated_at FROM chat_sessions "
            "ORDER BY updated_at DESC LIMIT ?;",
            (limit,),
        )
        return [
            {
                "id": r[0],
                "title": r[1],
                "agent_id": r[2],
                "created_at": r[3],
                "updated_at": r[4],
            }
            for r in rows
        ]

    def get_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.engine.execute_read(
            "SELECT id, role, content, model, created_at FROM chat_messages "
            "WHERE session_id = ? ORDER BY id ASC LIMIT ?;",
            (session_id, limit),
        )
        return [
            {
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "model": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        model: Optional[str] = None
    ):
        # Auto-create session if it doesn't exist
        self.engine.execute_write(
            "INSERT OR IGNORE INTO chat_sessions (id, title, agent_id) VALUES (?, ?, ?);",
            (session_id, content[:32] if role == "user" else "Conversation", "jarvis"),
        )
        self.engine.execute_write(
            "INSERT INTO chat_messages (session_id, role, content, model) VALUES (?, ?, ?, ?);",
            (session_id, role, content, model),
        )
        self.engine.execute_write(
            "UPDATE chat_sessions SET updated_at=CURRENT_TIMESTAMP WHERE id = ?;",
            (session_id,),
        )

    def delete_session(self, session_id: str):
        self.engine.execute_write("DELETE FROM chat_messages WHERE session_id = ?;", (session_id,))
        self.engine.execute_write("DELETE FROM chat_sessions WHERE id = ?;", (session_id,))


# Global singleton
session_manager = SessionManager()
