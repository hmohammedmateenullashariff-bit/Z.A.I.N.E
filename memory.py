"""
Z.A.I.N.E Agent — Persistent Memory & Context Buffer
Combines an in-session sliding window buffer with persistent SQLite storage
for long-term memories (user profile, preferences, key facts across restarts).
"""

import sqlite3
import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "zaine_tasks.db"


def _get_memory_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS task_learnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_summary TEXT NOT NULL,
            status TEXT NOT NULL,
            lesson_learned TEXT NOT NULL,
            keywords TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


def save_memory(key: str, value: str) -> str:
    """Saves or updates a permanent fact or user preference."""
    key = key.strip().lower()
    value = value.strip()
    if not key or not value:
        return "Error: key and value cannot be empty."

    conn = _get_memory_conn()
    conn.execute(
        """
        INSERT INTO memories (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, datetime.datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return f"Remembered: '{key}' = '{value}'"


def get_memory(key: str) -> str:
    """Retrieves a specific memory by key, or searches matching keys."""
    key = key.strip().lower()
    conn = _get_memory_conn()
    row = conn.execute("SELECT value FROM memories WHERE key = ?", (key,)).fetchone()
    if row:
        conn.close()
        return f"{key}: {row[0]}"

    # Fuzzy match if exact match not found
    rows = conn.execute(
        "SELECT key, value FROM memories WHERE key LIKE ? ORDER BY key",
        (f"%{key}%",),
    ).fetchall()
    conn.close()

    if not rows:
        return f"No memory found for '{key}'."
    return "\n".join(f"- {k}: {v}" for k, v in rows)


def get_all_memories() -> dict:
    """Returns a dict of all saved persistent memories."""
    conn = _get_memory_conn()
    rows = conn.execute("SELECT key, value FROM memories ORDER BY key").fetchall()
    conn.close()
    return {k: v for k, v in rows}


def record_task_learning(task_summary: str, status: str, lesson_learned: str, keywords: str) -> str:
    """Saves an acquired lesson, pattern, or technical insight from a task execution."""
    task_summary = task_summary.strip()
    lesson_learned = lesson_learned.strip()
    keywords = keywords.strip().lower()
    if not lesson_learned:
        return "Error: lesson_learned cannot be empty."

    conn = _get_memory_conn()
    conn.execute(
        """
        INSERT INTO task_learnings (task_summary, status, lesson_learned, keywords, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (task_summary, status, lesson_learned, keywords, datetime.datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return f"Learned lesson saved: {lesson_learned}"


def retrieve_relevant_learnings(user_query: str, limit: int = 3) -> list:
    """Finds past lessons learned that match keywords in the current user prompt."""
    import re
    words = re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", user_query.lower())
    stopwords = {"the", "and", "can", "you", "for", "with", "this", "that", "from", "how", "what", "where", "please", "zaine"}
    keywords = [w for w in words if w not in stopwords]
    if not keywords:
        return []

    conn = _get_memory_conn()
    clauses = []
    params = []
    for kw in keywords[:6]:
        clauses.append("(keywords LIKE ? OR task_summary LIKE ? OR lesson_learned LIKE ?)")
        params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])

    sql = f"SELECT DISTINCT lesson_learned FROM task_learnings WHERE ({' OR '.join(clauses)}) ORDER BY id DESC LIMIT {limit}"
    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [r[0] for r in rows]


def get_all_learnings(limit: int = 10) -> list:
    """Returns most recent task learnings."""
    conn = _get_memory_conn()
    rows = conn.execute("SELECT task_summary, lesson_learned, status FROM task_learnings ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows


def reflect_on_task_async(user_prompt: str, tool_history: list, outcome: str, model_name: str = "zaine"):
    """
    Runs in a background thread after a user interaction to analyze if a lesson or user preference
    should be permanently learned.
    """
    import threading
    import requests
    import json

    def _reflect():
        if len(user_prompt.strip().split()) <= 2 and not tool_history:
            return

        prompt = (
            f"You are a meta-cognition module for an AI assistant. Analyze this completed task:\n\n"
            f"User request: {user_prompt}\n"
            f"Tools executed: {json.dumps(tool_history) if tool_history else 'None'}\n"
            f"Final outcome: {outcome[:400]}\n\n"
            f"Did this task reveal a technical lesson, an error that was resolved, a user preference, or a specific workflow pattern?\n"
            f"If YES, formulate a concise, actionable 1-sentence lesson and 3-5 comma-separated keywords.\n"
            f"Format:\n"
            f"LESSON: <one concise actionable sentence>\n"
            f"KEYWORDS: <comma-separated keywords>\n\n"
            f"If this was just casual chitchat or trivial with nothing new learned, respond with: NONE"
        )
        try:
            resp = requests.post(
                "http://127.0.0.1:11434/api/generate",
                json={"model": model_name, "prompt": prompt, "stream": False},
                timeout=30,
            )
            if resp.status_code == 200:
                text = resp.json().get("response", "").strip()
                if "LESSON:" in text:
                    lesson_line = ""
                    kw_line = ""
                    for line in text.split("\n"):
                        if line.startswith("LESSON:"):
                            lesson_line = line.replace("LESSON:", "").strip()
                        elif line.startswith("KEYWORDS:"):
                            kw_line = line.replace("KEYWORDS:", "").strip()
                    if lesson_line:
                        record_task_learning(
                            task_summary=user_prompt[:150],
                            status="success",
                            lesson_learned=lesson_line,
                            keywords=kw_line or user_prompt[:50],
                        )
                        print(f"\n[Z.A.I.N.E learned a new lesson]: {lesson_line}")
        except Exception:
            pass

    threading.Thread(target=_reflect, daemon=True).start()


class ConversationMemory:
    def __init__(self, max_turns: int = 12):
        self.max_turns = max_turns
        self.history = []  # list of {"role": "user"/"assistant", "content": str}

    def add(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        # Keep only the last N turns (each turn = 1 user + 1 assistant message)
        max_messages = self.max_turns * 2
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]

    def get_messages(self):
        return list(self.history)

    def get_persistent_context(self, current_prompt: str = "") -> str:
        """Formats long-term memories, user profile, and relevant past task learnings for injection into the system prompt."""
        sections = []

        # 1. User Profile & Master Directives
        profile_path = Path(__file__).parent / "vault" / "user_profile.md"
        if profile_path.exists():
            try:
                prof_text = profile_path.read_text(encoding="utf-8", errors="ignore").strip()
                if prof_text:
                    sections.append(f"User Profile & Master Directives:\n{prof_text}")
            except Exception:
                pass

        # 2. Known facts and preferences from persistent SQLite storage
        mems = get_all_memories()
        if mems:
            lines = ["Known facts and user preferences (from persistent memory):"]
            for k, v in mems.items():
                lines.append(f"- {k}: {v}")
            sections.append("\n".join(lines))

        # 3. Dynamically inject relevant lessons from past tasks
        if current_prompt:
            learnings = retrieve_relevant_learnings(current_prompt, limit=3)
            if learnings:
                l_lines = ["Relevant lessons you previously learned from past tasks:"]
                for l in learnings:
                    l_lines.append(f"- {l}")
                sections.append("\n".join(l_lines))

        return "\n\n".join(sections)


    def clear(self):
        self.history = []

