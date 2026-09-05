"""
Z.A.I.N.E — Local Second Brain & Personal Knowledge Vault (Phase 4)
Provides 100% offline, private, and persistent knowledge retrieval:
- Fast SQLite FTS5 (Full-Text Search) with BM25 ranking
- Auto-syncs markdown (.md) and text (.txt) files in vault/
- Creates readable markdown files in vault/ for human editing
- Exposes tools: search_vault, add_to_vault, list_vault_documents
"""

import re
import sqlite3
import datetime
from pathlib import Path

VAULT_DIR = Path(__file__).parent / "vault"
DB_PATH = VAULT_DIR / "vault.db"


def _ensure_vault():
    """Initializes the vault directory and SQLite FTS5 database schema."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            tags TEXT DEFAULT '',
            content TEXT NOT NULL,
            filename TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            title,
            content,
            tags,
            category,
            content='notes',
            content_rowid='id'
        )
        """
    )

    # Trigger: after insert
    cur.execute(
        """
        CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
            INSERT INTO notes_fts(rowid, title, content, tags, category)
            VALUES (new.id, new.title, new.content, new.tags, new.category);
        END;
        """
    )

    # Trigger: after delete
    cur.execute(
        """
        CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, content, tags, category)
            VALUES('delete', old.id, old.title, old.content, old.tags, old.category);
        END;
        """
    )

    # Trigger: after update
    cur.execute(
        """
        CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, content, tags, category)
            VALUES('delete', old.id, old.title, old.content, old.tags, old.category);
            INSERT INTO notes_fts(rowid, title, content, tags, category)
            VALUES (new.id, new.title, new.content, new.tags, new.category);
        END;
        """
    )

    conn.commit()
    conn.close()


def _sanitize_filename(name: str) -> str:
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip().replace(" ", "_")
    return clean[:50] if clean else "note"


def sync_vault_files():
    """Scans vault/ for external markdown or text files and indexes new/updated ones."""
    _ensure_vault()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    now_iso = datetime.datetime.now().isoformat()
    for file_path in VAULT_DIR.glob("*.*"):
        if file_path.suffix.lower() not in (".md", ".txt") or file_path.name == "vault.db":
            continue

        try:
            mtime = datetime.datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
            title = file_path.stem.replace("_", " ").title()
            content = file_path.read_text(encoding="utf-8", errors="replace").strip()

            cur.execute("SELECT id, updated_at FROM notes WHERE filename = ?", (file_path.name,))
            row = cur.fetchone()

            if row is None:
                cur.execute(
                    "INSERT INTO notes (title, category, tags, content, filename, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, "vault_file", "", content, file_path.name, now_iso, mtime),
                )
            elif row[1] != mtime:
                cur.execute(
                    "UPDATE notes SET title = ?, content = ?, updated_at = ? WHERE id = ?",
                    (title, content, mtime, row[0]),
                )
        except Exception as e:
            print(f"[Vault Sync Warning]: Failed indexing {file_path.name}: {e}")

    conn.commit()
    conn.close()


def add_to_vault(title: str, content: str, category: str = "general", tags: str = "") -> str:
    """
    Saves a new note or document to Mateen's local Personal Vault (Second Brain).
    Writes a readable .md file in vault/ and indexes into SQLite FTS5 for instant search.
    """
    _ensure_vault()
    title_clean = title.strip()
    content_clean = content.strip()
    if not title_clean or not content_clean:
        return "Error: Note title and content cannot be empty."

    filename = f"{_sanitize_filename(title_clean)}.md"
    file_path = VAULT_DIR / filename
    now_iso = datetime.datetime.now().isoformat()

    # 1. Write human-readable markdown file
    header = f"# {title_clean}\n\n*Category: {category} | Tags: {tags} | Added: {now_iso[:10]}*\n\n---\n\n"
    file_path.write_text(header + content_clean + "\n", encoding="utf-8")

    # 2. Store in SQLite
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO notes (title, category, tags, content, filename, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title_clean, category.strip(), tags.strip(), content_clean, filename, now_iso, now_iso),
    )
    conn.commit()
    note_id = cur.lastrowid
    conn.close()

    return f"Saved to Vault [ID={note_id}, File='vault/{filename}'] (Title: '{title_clean}')"


def search_vault(query: str, limit: int = 4) -> str:
    """
    Searches across Mateen's Personal Vault documents using SQLite Full-Text Search.
    Returns matched excerpts with relevance ranking.
    """
    _ensure_vault()
    clean_q = query.strip()
    if not clean_q:
        return "Please provide a search term."

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # First try SQLite FTS5 MATCH with sanitized terms
    fts_terms = " OR ".join(f'"{term}"' for term in re.findall(r'\w+', clean_q) if len(term) > 1)
    results = []

    if fts_terms:
        try:
            cur.execute(
                """
                SELECT notes.id, notes.title, notes.category, notes.filename,
                       snippet(notes_fts, 1, '<b>', '</b>', '...', 25) as excerpt,
                       bm25(notes_fts) as rank
                FROM notes_fts
                JOIN notes ON notes.id = notes_fts.rowid
                WHERE notes_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_terms, limit),
            )
            results = cur.fetchall()
        except Exception:
            results = []

    # Fallback to standard LIKE matching if FTS5 had no matches or errored
    if not results:
        like_pattern = f"%{clean_q}%"
        cur.execute(
            """
            SELECT id, title, category, filename, SUBSTR(content, 1, 250) as excerpt, 0
            FROM notes
            WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
            LIMIT ?
            """,
            (like_pattern, like_pattern, like_pattern, limit),
        )
        results = cur.fetchall()

    conn.close()

    if not results:
        return f"No documents found in vault matching '{query}'."

    formatted = [f"Found {len(results)} note(s) in Vault for '{query}':"]
    for row in results:
        nid, ntitle, ncat, nfile, nexcerpt, _ = row
        clean_excerpt = nexcerpt.replace("<b>", "").replace("</b>", "").replace("\n", " ").strip()
        formatted.append(f"- **{ntitle}** [{ncat}] (vault/{nfile}):\n  \"{clean_excerpt}\"")

    return "\n\n".join(formatted)


def list_vault_documents() -> str:
    """Lists all documents, notes, and cheat sheets currently stored in the Vault."""
    _ensure_vault()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, title, category, filename, updated_at FROM notes ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return "Personal Vault is currently empty. You can add notes with add_to_vault()."

    lines = [f"Personal Vault Documents ({len(rows)} total):"]
    for row in rows:
        nid, ntitle, ncat, nfile, nup = row
        date_str = nup[:10] if nup else "N/A"
        lines.append(f"- [ID={nid}] **{ntitle}** ({ncat}) -> `vault/{nfile}` (Updated: {date_str})")

    return "\n".join(lines)


if __name__ == "__main__":
    _ensure_vault()
    # Add initial project architecture note if vault is empty
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM notes")
    count = cur.fetchone()[0]
    conn.close()

    if count == 0:
        add_to_vault(
            title="Project Z Architecture Overview",
            content="Z.A.I.N.E is built as a unified offline Jarvis assistant running locally on RTX 2050 GPU. Core components: Ollama (Qwen2.5 / Zaine persona), Faster-Whisper, Piper TTS, Telegram Mobile Bridge, SQLite persistent memories, and Personal Vault RAG.",
            category="architecture",
            tags="zaine, roadmap, ai, jarvis"
        )
    print("Vault initialized successfully.")
    print(list_vault_documents())
    print("\nTest search query 'architecture':")
    print(search_vault("architecture"))
