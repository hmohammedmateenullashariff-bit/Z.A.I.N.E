"""
Z.A.I.N.E — Idea Engine: Autonomous Creative Ideation System
Generates, stores, and manages creative ideas across 6 domains:
  - YouTube content concepts
  - Project-Z feature/capability ideas
  - Tech project concepts for Mateen
  - Business & monetization angles
  - Wild creative/cross-domain mashups
  - Learning paths & skill rabbit holes

Operates in two modes:
  1. Proactive: Overnight pipeline generates 5 ideas nightly → morning briefing
  2. On-demand: Tool call when user asks "give me ideas" / "kuch naya sochke bata"

Uses qwen2.5:3b (already pinned in VRAM) for synthesis. Zero extra dependencies.
Ideas are grounded in vault knowledge (60%) + creative wild thinking (40%).
"""

import os
import sys
import json
import time
import random
import sqlite3
import datetime
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "zaine_ideas.db"
DEFAULT_IDEA_COUNT = 5

# ── Idea Categories ──────────────────────────────────────────────────────
CATEGORIES = {
    "youtube": "YouTube Shorts/video content concepts, niche expansion, collab ideas, viral hooks",
    "project_z": "New Zaine capabilities, tools, integrations, architecture upgrades",
    "tech_project": "Side projects, apps, bots, automation tools Mateen could build",
    "business": "Monetization angles, SaaS concepts, freelance strategies, productized automation",
    "creative": "Wild unconventional ideas, cross-domain mashups, experimental moonshot concepts",
    "learning": "Skills to master, courses, certifications, deep-dive rabbit holes",
}

# ── Wild Card Cross-Domain Prompts (for the 40% creative injection) ─────
WILD_CARD_PROMPTS = [
    "What if you combined AI with physical fitness tracking in an unexpected way?",
    "Think of a tool that would make a university student's life 10x easier using local LLMs.",
    "Imagine a YouTube channel concept that has never been tried before in the Shorts space.",
    "What automation could save 2 hours per day for a solo developer-creator?",
    "Think of a creative way to use edge AI (3B parameter models) that nobody has commercialized yet.",
    "What if voice assistants could do something they currently can't — what would be most impactful?",
    "Combine two unrelated fields (e.g. cooking + cryptography, music + DevOps) into a viable product.",
    "What open-source project would get 1000 GitHub stars in its first month if built well?",
    "Think of something a 4GB VRAM laptop could do that cloud-only solutions cannot.",
    "What's a business that could be built entirely by one person + their AI assistant?",
    "What YouTube content would go viral in the Pakistani/South Asian tech creator space?",
    "Imagine a Telegram bot that solves a real daily problem nobody has automated yet.",
    "What if you could train a tiny model to be world-class at exactly one niche task?",
    "Think of a hardware + software project under $50 total cost that would impress at a hackathon.",
    "What's the most creative use of browser automation + AI for content research?",
    "Combine anime aesthetics with productivity tools — what would that look like?",
    "What developer tool would you pay for if it existed, but nobody has built it?",
    "Think of a way to make money while you sleep using only free-tier cloud services.",
    "What if screen recording + AI could generate something more useful than just a video?",
    "Imagine a personal knowledge management system that actually works unlike the rest.",
]


# =====================================================================
# DATABASE LAYER
# =====================================================================
_db_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    """Returns a connection to the ideas database, creating schema if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS zaine_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            reasoning TEXT NOT NULL,
            grounded_source TEXT DEFAULT 'creative_synthesis',
            status TEXT DEFAULT 'NEW',
            created_at TEXT NOT NULL,
            starred_at TEXT
        )
    """)
    conn.commit()
    return conn


def _store_idea(category: str, title: str, description: str,
                reasoning: str, grounded_source: str = "creative_synthesis") -> int:
    """Inserts a new idea into the database. Returns the idea ID."""
    now = datetime.datetime.now().isoformat()
    with _db_lock:
        conn = _get_db()
        cur = conn.execute(
            """INSERT INTO zaine_ideas (category, title, description, reasoning, grounded_source, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'NEW', ?)""",
            (category, title, description, reasoning, grounded_source, now)
        )
        idea_id = cur.lastrowid
        conn.commit()
        conn.close()
    return idea_id


def _is_duplicate(title: str, lookback_days: int = 30) -> bool:
    """Checks if a similar idea title already exists in the last N days."""
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=lookback_days)).isoformat()
    # Extract significant keywords (3+ chars) from title
    title_words = {w.lower() for w in title.split() if len(w) >= 3}
    if len(title_words) < 2:
        return False  # Too short to meaningfully compare

    with _db_lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT title FROM zaine_ideas WHERE created_at > ?", (cutoff,)
        ).fetchall()
        conn.close()

    for (existing_title,) in rows:
        existing_words = {w.lower() for w in existing_title.split() if len(w) >= 3}
        if not existing_words:
            continue
        overlap = len(title_words & existing_words) / max(len(title_words), len(existing_words))
        if overlap >= 0.6:  # 60% keyword overlap = duplicate
            return True
    return False


# =====================================================================
# CONTEXT SEED GATHERING
# =====================================================================
def _gather_context_seeds() -> Dict[str, List[str]]:
    """Collects grounded context seeds from vault knowledge, AI intel, and memory."""
    seeds = {
        "ai_trends": [],
        "tech_knowledge": [],
        "past_interests": [],
        "tools_capabilities": [],
    }

    # 1. Daily AI Intel (latest breakthroughs)
    intel_path = PROJECT_ROOT / "vault" / "knowledge" / "daily_ai_intel.md"
    if intel_path.exists():
        try:
            text = intel_path.read_text(encoding="utf-8")
            # Extract key topic lines
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("- **") or line.startswith("**"):
                    seeds["ai_trends"].append(line[:120])
                if len(seeds["ai_trends"]) >= 5:
                    break
        except Exception:
            pass

    # 2. Knowledge vault topics (algorithms, system design, etc.)
    vault_dir = PROJECT_ROOT / "data" / "knowledge_vault"
    if vault_dir.exists():
        try:
            for json_file in vault_dir.glob("*.json"):
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data[:3]:
                        name = item.get("name") or item.get("title") or ""
                        if name:
                            seeds["tech_knowledge"].append(f"{json_file.stem}: {name}")
                elif isinstance(data, dict):
                    for key in list(data.keys())[:3]:
                        seeds["tech_knowledge"].append(f"{json_file.stem}: {key}")
        except Exception:
            pass

    # 3. Recent task learnings (what Mateen has been working on)
    try:
        import memory as mem_module
        conn = mem_module._get_memory_conn()
        rows = conn.execute(
            "SELECT lesson FROM task_learnings ORDER BY id DESC LIMIT 5"
        ).fetchall()
        conn.close()
        for (lesson,) in rows:
            seeds["past_interests"].append(lesson[:100])
    except Exception:
        pass

    # 4. Zaine's own tool capabilities (for Project-Z feature ideas)
    seeds["tools_capabilities"] = [
        "Zaine has: voice TTS, vision (moondream), YouTube automation, Telegram bridge",
        "Zaine has: code review, toolmaker, browser automation, hive mind multi-agent",
        "Zaine has: overnight pipeline, morning briefing, daily AI intel harvester",
        "Zaine has: approval system, vault/knowledge store, episodic memory",
        "Zaine runs on: 4GB VRAM RTX 2050, qwen2.5:3b pinned, deepseek-r1:7b available",
    ]

    return seeds


# =====================================================================
# IDEA GENERATION (qwen2.5:3b)
# =====================================================================
def _build_ideation_prompt(seeds: Dict[str, List[str]], count: int = 5,
                           focus: str = "", categories: Optional[List[str]] = None) -> str:
    """Builds the structured prompt for qwen2.5:3b to generate ideas."""
    cat_list = categories or list(CATEGORIES.keys())
    cat_descriptions = "\n".join(f"  - {c}: {CATEGORIES[c]}" for c in cat_list if c in CATEGORIES)

    # Select random wild card prompts for creative injection
    wild_cards = random.sample(WILD_CARD_PROMPTS, min(3, len(WILD_CARD_PROMPTS)))

    # Format context seeds
    seed_text_parts = []
    if seeds.get("ai_trends"):
        seed_text_parts.append("Recent AI trends:\n" + "\n".join(f"  {s}" for s in seeds["ai_trends"][:4]))
    if seeds.get("tech_knowledge"):
        picked = random.sample(seeds["tech_knowledge"], min(4, len(seeds["tech_knowledge"])))
        seed_text_parts.append("Technical knowledge topics:\n" + "\n".join(f"  {s}" for s in picked))
    if seeds.get("past_interests"):
        seed_text_parts.append("Recent user interests:\n" + "\n".join(f"  {s}" for s in seeds["past_interests"][:3]))
    if seeds.get("tools_capabilities"):
        picked = random.sample(seeds["tools_capabilities"], min(2, len(seeds["tools_capabilities"])))
        seed_text_parts.append("System capabilities:\n" + "\n".join(f"  {s}" for s in picked))

    seed_text = "\n\n".join(seed_text_parts) if seed_text_parts else "No specific context available."

    focus_line = f"\nFOCUS AREA: The user specifically wants ideas about: {focus}\n" if focus else ""

    prompt = f"""You are Z.A.I.N.E's Idea Engine — a creative strategist generating fresh, actionable ideas for Mateen (a CS student, solo developer-creator, and AI enthusiast building his own local AI assistant on a 4GB VRAM laptop).

CONTEXT SEEDS (use these for grounded ideas):
{seed_text}

CREATIVE WILD CARDS (use these for out-of-the-box ideas):
{chr(10).join(f'  - {w}' for w in wild_cards)}
{focus_line}
IDEA CATEGORIES:
{cat_descriptions}

Generate exactly {count} unique, specific, and actionable ideas. Mix practical grounded ideas (inspired by the context seeds) with creative wild ideas (inspired by the wild cards).

Each idea MUST be specific and detailed — not generic. Bad: "Make a YouTube video about AI". Good: "Create a YouTube Shorts series showing side-by-side comparisons of the same prompt answered by 5 different local LLMs (qwen, deepseek, phi, llama, gemma) — visual speed + quality races".

Respond in this exact JSON format (no extra text):
[
  {{
    "category": "<one of: {', '.join(cat_list)}>",
    "title": "<concise catchy title, max 12 words>",
    "description": "<2-3 sentence detailed description of the idea>",
    "reasoning": "<1 sentence on why this is worth pursuing NOW>",
    "grounded_source": "<which context seed inspired this, or 'creative_synthesis' for wild ideas>"
  }}
]"""
    return prompt


def _call_qwen_for_ideas(prompt: str) -> List[Dict[str, str]]:
    """Calls qwen2.5:3b via Ollama to generate ideas."""
    try:
        import requests
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen2.5:3b",
                "messages": [
                    {"role": "system", "content": "You are a creative idea generator. Always respond with valid JSON arrays only."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.85,
                    "num_predict": 1200,
                    "top_p": 0.92,
                },
            },
            timeout=45,
        )
        if resp.status_code != 200:
            print(f"[IdeaEngine] Ollama error: {resp.status_code}")
            return []

        content = resp.json().get("message", {}).get("content", "")

        # Extract JSON array from response (handle markdown code blocks)
        content = content.strip()
        if content.startswith("```"):
            # Strip code fence
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            content = content.strip()

        ideas = json.loads(content)
        if isinstance(ideas, list):
            return ideas
        return []

    except json.JSONDecodeError as e:
        print(f"[IdeaEngine] JSON parse error: {e}")
        return []
    except Exception as e:
        print(f"[IdeaEngine] Generation error: {e}")
        return []


# =====================================================================
# PUBLIC API
# =====================================================================
def generate_ideas(count: int = DEFAULT_IDEA_COUNT, categories: Optional[List[str]] = None,
                   focus: str = "") -> List[Dict[str, Any]]:
    """
    Generates fresh ideas using qwen2.5:3b, deduplicates against history,
    and stores accepted ideas in the database.

    Args:
        count: Number of ideas to generate (default 5)
        categories: Optional list of categories to focus on
        focus: Optional user-specified focus topic

    Returns:
        List of accepted idea dicts with their database IDs
    """
    print(f"[IdeaEngine] Generating {count} ideas...")

    seeds = _gather_context_seeds()
    prompt = _build_ideation_prompt(seeds, count=count + 2, focus=focus, categories=categories)
    raw_ideas = _call_qwen_for_ideas(prompt)

    if not raw_ideas:
        print("[IdeaEngine] No ideas generated from model. Using fallback.")
        return []

    accepted = []
    for idea in raw_ideas:
        title = idea.get("title", "").strip()
        category = idea.get("category", "creative").strip().lower()
        description = idea.get("description", "").strip()
        reasoning = idea.get("reasoning", "").strip()
        grounded_source = idea.get("grounded_source", "creative_synthesis").strip()

        if not title or not description:
            continue

        # Validate category
        if category not in CATEGORIES:
            category = "creative"

        # Dedup check
        if _is_duplicate(title):
            print(f"[IdeaEngine] Skipping duplicate: {title[:50]}...")
            continue

        idea_id = _store_idea(category, title, description, reasoning, grounded_source)
        accepted.append({
            "id": idea_id,
            "category": category,
            "title": title,
            "description": description,
            "reasoning": reasoning,
            "grounded_source": grounded_source,
        })

        if len(accepted) >= count:
            break

    print(f"[IdeaEngine] Accepted {len(accepted)} / {len(raw_ideas)} ideas (dedup filtered)")
    return accepted


def get_daily_ideas(count: int = DEFAULT_IDEA_COUNT) -> str:
    """
    Proactive nightly generation for morning briefing injection.
    Returns formatted markdown string.
    """
    ideas = generate_ideas(count=count)
    if not ideas:
        return "No fresh ideas generated tonight. Will try again tomorrow."

    lines = []
    category_emoji = {
        "youtube": "🎬", "project_z": "🤖", "tech_project": "💻",
        "business": "💰", "creative": "🌀", "learning": "📚",
    }
    for i, idea in enumerate(ideas, 1):
        emoji = category_emoji.get(idea["category"], "💡")
        lines.append(
            f"- {emoji} **[{idea['category'].upper()}] {idea['title']}** (#{idea['id']})\n"
            f"  {idea['description']}\n"
            f"  _Why now: {idea['reasoning']}_"
        )
    return "\n".join(lines)


def get_ideas_on_demand(focus: str = "", count: int = 5) -> str:
    """
    On-demand idea generation for tool call.
    Returns formatted string suitable for chat response.
    """
    ideas = generate_ideas(count=count, focus=focus)
    if not ideas:
        return "Couldn't generate ideas right now. Ollama might be busy — try again in a moment."

    category_emoji = {
        "youtube": "🎬", "project_z": "🤖", "tech_project": "💻",
        "business": "💰", "creative": "🌀", "learning": "📚",
    }

    lines = [f"💡 **Fresh Ideas from Z.A.I.N.E's Idea Engine:**\n"]
    for i, idea in enumerate(ideas, 1):
        emoji = category_emoji.get(idea["category"], "💡")
        lines.append(
            f"{i}. {emoji} **{idea['title']}** `[{idea['category'].upper()}]` `#{idea['id']}`\n"
            f"   {idea['description']}\n"
            f"   > _Why: {idea['reasoning']}_\n"
        )

    lines.append(f"_Star an idea with `star_idea(<id>)` to save it as a favorite._")
    return "\n".join(lines)


def list_ideas(category: str = "", status: str = "NEW", limit: int = 10) -> str:
    """Lists stored ideas from the database."""
    with _db_lock:
        conn = _get_db()
        query = "SELECT id, category, title, description, reasoning, status, created_at FROM zaine_ideas WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category.lower())
        if status:
            query += " AND status = ?"
            params.append(status.upper())
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        conn.close()

    if not rows:
        return f"No ideas found (category={category or 'all'}, status={status or 'all'})."

    category_emoji = {
        "youtube": "🎬", "project_z": "🤖", "tech_project": "💻",
        "business": "💰", "creative": "🌀", "learning": "📚",
    }

    lines = [f"📋 **Stored Ideas ({len(rows)} found):**\n"]
    for row in rows:
        idea_id, cat, title, desc, reasoning, st, created = row
        emoji = category_emoji.get(cat, "💡")
        star = "⭐" if st == "STARRED" else ""
        lines.append(f"- {emoji} `#{idea_id}` {star} **{title}** [{cat.upper()}] ({st})\n  {desc[:120]}...")
    return "\n".join(lines)


def star_idea(idea_id: int) -> str:
    """Marks an idea as starred/favorite."""
    now = datetime.datetime.now().isoformat()
    with _db_lock:
        conn = _get_db()
        row = conn.execute("SELECT title, status FROM zaine_ideas WHERE id = ?", (idea_id,)).fetchone()
        if not row:
            conn.close()
            return f"Idea #{idea_id} not found."
        if row[1] == "STARRED":
            conn.close()
            return f"Idea #{idea_id} ('{row[0]}') is already starred ⭐"
        conn.execute(
            "UPDATE zaine_ideas SET status = 'STARRED', starred_at = ? WHERE id = ?",
            (now, idea_id)
        )
        conn.commit()
        conn.close()
    return f"⭐ Starred idea #{idea_id}: '{row[0]}'"


def archive_idea(idea_id: int) -> str:
    """Archives an idea (marks as ARCHIVED)."""
    with _db_lock:
        conn = _get_db()
        row = conn.execute("SELECT title FROM zaine_ideas WHERE id = ?", (idea_id,)).fetchone()
        if not row:
            conn.close()
            return f"Idea #{idea_id} not found."
        conn.execute("UPDATE zaine_ideas SET status = 'ARCHIVED' WHERE id = ?", (idea_id,))
        conn.commit()
        conn.close()
    return f"📦 Archived idea #{idea_id}: '{row[0]}'"


def get_idea_stats() -> Dict[str, Any]:
    """Returns statistics about stored ideas."""
    with _db_lock:
        conn = _get_db()
        total = conn.execute("SELECT COUNT(*) FROM zaine_ideas").fetchone()[0]
        by_status = dict(conn.execute(
            "SELECT status, COUNT(*) FROM zaine_ideas GROUP BY status"
        ).fetchall())
        by_category = dict(conn.execute(
            "SELECT category, COUNT(*) FROM zaine_ideas GROUP BY category"
        ).fetchall())
        conn.close()
    return {"total": total, "by_status": by_status, "by_category": by_category}


# =====================================================================
# CLI ENTRY POINT & SELF-TEST
# =====================================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Z.A.I.N.E Idea Engine")
    parser.add_argument("--count", type=int, default=3, help="Number of ideas to generate")
    parser.add_argument("--focus", type=str, default="", help="Optional focus topic")
    parser.add_argument("--list", action="store_true", help="List stored ideas")
    parser.add_argument("--stats", action="store_true", help="Show idea statistics")
    parser.add_argument("--test", action="store_true", help="Run self-test")
    args = parser.parse_args()

    if args.test:
        print("=== Idea Engine Self-Test ===\n")

        # Test 1: DB schema
        print("Test 1: Database schema creation...")
        conn = _get_db()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        assert any(t[0] == "zaine_ideas" for t in tables), "zaine_ideas table not created!"
        conn.close()
        print("  ✅ zaine_ideas table created\n")

        # Test 2: Store and retrieve
        print("Test 2: Store and retrieve idea...")
        test_id = _store_idea("tech_project", "Test Idea Engine", "A test idea for verification", "Testing the system", "self_test")
        assert test_id > 0, "Failed to store idea!"
        print(f"  ✅ Stored idea #{test_id}\n")

        # Test 3: Deduplication
        print("Test 3: Deduplication check...")
        assert _is_duplicate("Test Idea Engine"), "Dedup should catch exact title!"
        assert not _is_duplicate("Completely Different Topic About Cooking"), "Should not flag unrelated title!"
        print("  ✅ Dedup correctly identifies duplicates\n")

        # Test 4: Star and archive
        print("Test 4: Star and archive...")
        result = star_idea(test_id)
        assert "Starred" in result, f"Star failed: {result}"
        result = archive_idea(test_id)
        assert "Archived" in result, f"Archive failed: {result}"
        print("  ✅ Star and archive working\n")

        # Test 5: Context seed gathering
        print("Test 5: Context seed gathering...")
        seeds = _gather_context_seeds()
        assert isinstance(seeds, dict), "Seeds should be a dict"
        assert "tools_capabilities" in seeds, "Should have tools_capabilities"
        print(f"  ✅ Gathered seeds: {', '.join(f'{k}({len(v)})' for k, v in seeds.items())}\n")

        # Test 6: Stats
        print("Test 6: Statistics...")
        stats = get_idea_stats()
        assert stats["total"] >= 1, "Should have at least 1 idea"
        print(f"  ✅ Stats: {stats}\n")

        print("=== All Self-Tests Passed ===")

    elif args.list:
        print(list_ideas())

    elif args.stats:
        stats = get_idea_stats()
        print(f"Total ideas: {stats['total']}")
        print(f"By status: {stats['by_status']}")
        print(f"By category: {stats['by_category']}")

    else:
        print(get_ideas_on_demand(focus=args.focus, count=args.count))
