"""
Z.A.I.N.E Agent — Persistent Memory & Context Buffer
Combines an in-session sliding window buffer with persistent SQLite storage
for long-term memories (user profile, preferences, key facts across restarts).
"""

import sqlite3
import datetime
import threading
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

DB_PATH = Path(__file__).parent / "zaine_tasks.db"

_EPISODE_QUEUE_LOCK = threading.Lock()
_EPISODE_PENDING_QUEUE: List[Tuple[list, str, str, str]] = []
_EPISODE_THREAD_ACTIVE = False



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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_start TEXT NOT NULL,
            session_end TEXT NOT NULL,
            topic_summary TEXT NOT NULL,
            key_points TEXT NOT NULL,
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


def reflect_on_task_async(user_prompt: str, tool_history: list, outcome: str, model_name: str = "qwen2.5:3b"):
    """
    Runs in a background thread with an idle grace delay to analyze if an insight
    or user preference should be permanently committed, without blocking active voice conversation.
    """
    import threading
    import requests
    import json
    import time

    def _reflect():
        # Skip trivial or casual prompts
        clean_p = user_prompt.strip().lower()
        if len(clean_p.split()) <= 2 and not tool_history:
            return
        if any(clean_p.startswith(w) for w in ["hi", "hello", "hey", "status", "who are you", "what time", "test"]):
            if not tool_history or all("system_status" in str(t) for t in tool_history):
                return

        # Idle grace delay: wait 2.0s so we never collide with immediate follow-up user speech
        time.sleep(2.0)

        prompt = (
            f"Analyze this completed assistant interaction:\n"
            f"User: {user_prompt}\n"
            f"Tools: {json.dumps(tool_history) if tool_history else 'None'}\n"
            f"Outcome: {outcome[:300]}\n\n"
            f"Did this reveal a specific user preference, solved error, or new workflow insight?\n"
            f"If YES, format as:\n"
            f"LESSON: <one concise actionable sentence>\n"
            f"KEYWORDS: <comma-separated keywords>\n"
            f"If NO new insight or standard query, respond with: NONE"
        )
        try:
            resp = requests.post(
                "http://127.0.0.1:11434/api/generate",
                json={"model": model_name, "prompt": prompt, "stream": False, "options": {"num_predict": 128}},
                timeout=15,
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
                    if lesson_line and "none" not in lesson_line.lower():
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


def record_conversation_episode(
    session_start: str,
    session_end: str,
    topic_summary: str,
    key_points: str,
    keywords: str
) -> str:
    """Inserts a structured episodic narrative summary into conversation_episodes."""
    topic_summary = topic_summary.strip()
    key_points = key_points.strip()
    keywords = keywords.strip().lower()
    if not topic_summary:
        return "Error: topic_summary cannot be empty."

    conn = _get_memory_conn()
    conn.execute(
        """
        INSERT INTO conversation_episodes (session_start, session_end, topic_summary, key_points, keywords, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_start, session_end, topic_summary, key_points, keywords, datetime.datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return f"Episode recorded: {topic_summary}"


def retrieve_relevant_episodes(user_query: str, limit: int = 2) -> List[Dict[str, str]]:
    """
    Finds past conversational episodes matching keywords in the current user prompt.
    Reuses the same SQL LIKE keyword-matching pattern as retrieve_relevant_learnings.
    """
    import re
    words = re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", user_query.lower())
    stopwords = {
        "the", "and", "can", "you", "for", "with", "this", "that", "from",
        "how", "what", "where", "please", "zaine", "last", "time", "about",
        "tell", "know", "when", "were", "have", "been", "talked", "discussed"
    }
    keywords = [w for w in words if w not in stopwords]
    if not keywords:
        return []

    conn = _get_memory_conn()
    clauses = []
    params = []
    for kw in keywords[:6]:
        clauses.append("(keywords LIKE ? OR topic_summary LIKE ? OR key_points LIKE ?)")
        params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])

    sql = f"SELECT topic_summary, key_points, created_at FROM conversation_episodes WHERE ({' OR '.join(clauses)}) ORDER BY id DESC LIMIT {limit}"
    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception:
        rows = []
    conn.close()

    results = []
    for r in rows:
        results.append({
            "topic_summary": r[0],
            "key_points": r[1],
            "created_at": r[2]
        })
    return results


def get_last_session_episode() -> Optional[Dict[str, str]]:
    """Fetches the single most recent conversation episode regardless of query."""
    conn = _get_memory_conn()
    try:
        row = conn.execute(
            "SELECT topic_summary, key_points, created_at FROM conversation_episodes ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except Exception:
        row = None
    conn.close()
    if row:
        return {
            "topic_summary": row[0],
            "key_points": row[1],
            "created_at": row[2]
        }
    return None


def get_daily_substantive_episode(date_str: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Queries conversation_episodes for the day's most substantive topic
    (evaluated by highest keyword count or longest key_points).
    Returns None if no substantive episodes exist for that day.
    """
    if not date_str:
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    conn = _get_memory_conn()
    try:
        rows = conn.execute(
            "SELECT id, topic_summary, key_points, keywords, created_at FROM conversation_episodes WHERE created_at LIKE ? ORDER BY id DESC",
            (f"{date_str}%",)
        ).fetchall()
    except Exception:
        rows = []
    conn.close()

    if not rows:
        return None

    best_episode = None
    best_score = -1

    for r in rows:
        topic_summary = (r[1] or "").strip()
        key_points = (r[2] or "").strip()
        keywords = (r[3] or "").strip()
        if not topic_summary:
            continue

        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        kw_count = len(kw_list)
        kp_len = len(key_points)

        # Skip trivial or empty episodes (must have meaningful content)
        if kw_count == 0 and kp_len < 20:
            continue

        score = (kw_count * 10) + kp_len
        if score > best_score:
            best_score = score
            best_episode = {
                "id": r[0],
                "topic_summary": topic_summary,
                "key_points": key_points,
                "keywords": keywords,
                "created_at": r[4],
                "score": score
            }

    return best_episode


def summarize_and_store_episode_async(
    dropped_turns: list,
    session_start: str = "",
    session_end: str = "",
    model_name: str = "qwen2.5:3b"
):
    """
    Asynchronously summarizes outgoing conversation turns pruned on FIFO trim.
    Applies casual-chat filter to reject trivial exchanges.
    Guarded by a module-level lock and queue to prevent concurrent thread stampedes on Ollama.
    """
    global _EPISODE_THREAD_ACTIVE

    with _EPISODE_QUEUE_LOCK:
        _EPISODE_PENDING_QUEUE.append((dropped_turns, session_start, session_end, model_name))
        if _EPISODE_THREAD_ACTIVE:
            # Running worker thread will process this queued batch before exiting
            return
        _EPISODE_THREAD_ACTIVE = True

    def _worker():
        global _EPISODE_THREAD_ACTIVE
        import requests
        import json
        import time

        try:
            while True:
                with _EPISODE_QUEUE_LOCK:
                    if not _EPISODE_PENDING_QUEUE:
                        _EPISODE_THREAD_ACTIVE = False
                        break
                    batch_item = _EPISODE_PENDING_QUEUE.pop(0)

                turns, start_ts, end_ts, m_name = batch_item

                # 1. Casual-chat filter: inspect user prompts across dropped turns
                user_texts = [t.get("content", "").strip() for t in turns if t.get("role") == "user"]
                total_user_words = sum(len(text.split()) for text in user_texts)
                if total_user_words < 12:
                    continue

                # Skip if every user turn starts with casual greetings or status checks
                trivial_starters = ["hi", "hello", "hey", "status", "who are you", "what time", "test", "clear", "ping"]
                all_trivial = True
                for text in user_texts:
                    lower = text.lower()
                    if not any(lower.startswith(w) for w in trivial_starters):
                        all_trivial = False
                        break
                if all_trivial:
                    continue

                # 2. Idle grace delay: 2.5s to avoid colliding with active speech/turn
                time.sleep(2.5)

                # 3. Build dialogue representation
                dialogue_lines = []
                for t in turns:
                    speaker = "Mateen" if t.get("role") == "user" else "Zaine"
                    dialogue_lines.append(f"{speaker}: {t.get('content', '')}")
                dialogue_text = "\n".join(dialogue_lines)

                prompt = (
                    "You are an expert conversation archivist. Analyze these conversation turns between Mateen and assistant Zaine:\n\n"
                    f"{dialogue_text[:1200]}\n\n"
                    "Produce a concise episodic narrative memory in this exact format:\n"
                    "TOPIC_SUMMARY: <1-2 concise sentences summarizing the key subject, personal updates, or decisions made>\n"
                    "KEY_POINTS: <bullet list of 2-3 specific details, topics, or preferences mentioned>\n"
                    "KEYWORDS: <comma-separated search keywords>\n"
                    "If no meaningful conversation took place, reply with: NONE"
                )

                try:
                    resp = requests.post(
                        "http://127.0.0.1:11434/api/generate",
                        json={
                            "model": m_name,
                            "prompt": prompt,
                            "stream": False,
                            "options": {"num_predict": 150, "temperature": 0.3}
                        },
                        timeout=18,
                    )
                    if resp.status_code == 200:
                        text = resp.json().get("response", "").strip()
                        if "TOPIC_SUMMARY:" in text and "none" not in text.lower()[:30]:
                            topic_summary = ""
                            key_points = ""
                            keywords = ""
                            current_section = None
                            kp_lines = []

                            for line in text.split("\n"):
                                s_line = line.strip()
                                if s_line.startswith("TOPIC_SUMMARY:"):
                                    topic_summary = s_line.replace("TOPIC_SUMMARY:", "").strip()
                                    current_section = "TOPIC"
                                elif s_line.startswith("KEY_POINTS:"):
                                    first_p = s_line.replace("KEY_POINTS:", "").strip()
                                    if first_p:
                                        kp_lines.append(first_p)
                                    current_section = "POINTS"
                                elif s_line.startswith("KEYWORDS:"):
                                    keywords = s_line.replace("KEYWORDS:", "").strip()
                                    current_section = "KEYWORDS"
                                elif current_section == "POINTS" and s_line:
                                    kp_lines.append(s_line)

                            key_points = "\n".join(kp_lines).strip()
                            if not keywords and user_texts:
                                keywords = ", ".join(user_texts[0].split()[:5])

                            if topic_summary:
                                s_ts = start_ts or datetime.datetime.now().isoformat()
                                e_ts = end_ts or datetime.datetime.now().isoformat()
                                record_conversation_episode(
                                    session_start=s_ts,
                                    session_end=e_ts,
                                    topic_summary=topic_summary,
                                    key_points=key_points,
                                    keywords=keywords
                                )
                                print(f"\n[Z.A.I.N.E archived conversation episode]: {topic_summary}")
                except Exception:
                    pass
        finally:
            with _EPISODE_QUEUE_LOCK:
                _EPISODE_THREAD_ACTIVE = False

    threading.Thread(target=_worker, daemon=True).start()



class ConversationMemory:
    def __init__(self, max_turns: int = 12):
        self.max_turns = max_turns
        self.history = []  # list of {"role": "user"/"assistant", "content": str, "timestamp": str}
        self.session_start = datetime.datetime.now().isoformat()
        self.session_recalled = False

    def clear(self):
        """Resets in-memory conversation turn history."""
        self.history.clear()
        self.session_recalled = False

    def add(self, role: str, content: str):
        now_ts = datetime.datetime.now().isoformat()
        self.history.append({"role": role, "content": content, "timestamp": now_ts})
        max_messages = self.max_turns * 2
        if len(self.history) > max_messages:
            dropped = self.history[:-max_messages]
            self.history = self.history[-max_messages:]
            # Non-blocking async background episode summarization of the pruned batch
            start_ts = dropped[0].get("timestamp", self.session_start)
            end_ts = dropped[-1].get("timestamp", now_ts)
            summarize_and_store_episode_async(
                dropped_turns=dropped,
                session_start=start_ts,
                session_end=end_ts
            )

    def get_messages(self):
        return [{"role": m["role"], "content": m["content"]} for m in self.history]

    def get_persistent_context(self, current_prompt: str = "") -> str:
        """Formats long-term memories, user profile, relevant task learnings, and episodic conversation history."""
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

        # 3. Technical lessons from past task execution (Strictly Task Heuristics)
        if current_prompt:
            learnings = retrieve_relevant_learnings(current_prompt, limit=3)
            if learnings:
                l_lines = ["Relevant lessons you previously learned from past tasks:"]
                for l in learnings:
                    l_lines.append(f"- {l}")
                sections.append("\n".join(l_lines))

        # 4. First-turn Last Session Recall (Narrative continuity)
        if not self.session_recalled:
            last_ep = get_last_session_episode()
            if last_ep and last_ep.get("topic_summary"):
                sections.append(f"Last time we talked about: {last_ep['topic_summary']}")
            self.session_recalled = True

        # 5. Relevant context from past conversations (Strictly Episodic Recall)
        if current_prompt:
            episodes = retrieve_relevant_episodes(current_prompt, limit=2)
            if episodes:
                e_lines = ["Relevant context from past conversations:"]
                for ep in episodes:
                    summary = ep.get("topic_summary", "")
                    pts = ep.get("key_points", "")
                    if pts:
                        e_lines.append(f"- Previous Discussion: {summary}\n  Details: {pts}")
                    else:
                        e_lines.append(f"- Previous Discussion: {summary}")
                sections.append("\n".join(e_lines))

        return "\n\n".join(sections)

    def clear(self):
        self.history = []
        self.session_start = datetime.datetime.now().isoformat()
        self.session_recalled = False


