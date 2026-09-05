"""
Z.A.I.N.E — Developer Knowledge Engine
Unified SQLite FTS5 BM25 search and retrieval engine across 17 world-class developer repositories:
- The Algorithms (TheAlgorithms/Python)
- System Design Primer (donnemartin/system-design-primer)
- Build Your Own X (codecrafters-io/build-your-own-x)
- Free For Dev (ripienaar/free-for-dev)
- Open Source Alternatives (RunaCapital/awesome-oss-alternatives)
- Roadmap.sh (kamranahmedse/developer-roadmap)
- Computer Science Curriculum (ossu/computer-science)
- LLMs From Scratch (rasbt/LLMs-from-scratch)
- ML From Scratch (eriklindernoren/ML-From-Scratch)
- Papers We Love (papers-we-love/papers-we-love)
- Free Programming Books, Best Websites, Engineering Blogs & The Awesome Meta-Index
"""

import json
import os
import sqlite3
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_DIR = os.path.join(BASE_DIR, "data", "knowledge_vault")
DB_PATH = os.path.join(BASE_DIR, "data", "knowledge_vault.db")


class KnowledgeEngine:
    """High-speed local FTS5 search and retrieval engine for developer knowledge."""

    def __init__(self, db_path: str = DB_PATH, vault_dir: str = VAULT_DIR):
        self.db_path = db_path
        self.vault_dir = vault_dir
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes FTS5 virtual table and populates data from JSON files if needed."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                    source_domain,
                    category,
                    title,
                    content,
                    metadata_json,
                    tokenize='porter unicode61'
                )
                """
            )
            # Check if populated
            cursor.execute("SELECT count(*) FROM knowledge_fts")
            count = cursor.fetchone()[0]
            if count == 0:
                self._index_all_vault_files(conn)

    def _index_all_vault_files(self, conn: sqlite3.Connection):
        """Indexes all JSON datasets in the vault directory into SQLite FTS5."""
        if not os.path.exists(self.vault_dir):
            return

        cursor = conn.cursor()
        for filename in os.listdir(self.vault_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.vault_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            domain = filename.replace(".json", "")
            if isinstance(data, list):
                for item in data:
                    title = item.get("name") or item.get("topic") or item.get("system") or item.get("title") or item.get("role") or item.get("proprietary") or item.get("category", "")
                    category = item.get("category") or item.get("field") or item.get("area", domain)
                    content_str = json.dumps(item, ensure_ascii=False)
                    cursor.execute(
                        """
                        INSERT INTO knowledge_fts (source_domain, category, title, content, metadata_json)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (domain, category, str(title), content_str, json.dumps(item)),
                    )
        conn.commit()

    def search(self, query: str, domain: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Executes a BM25 ranked FTS5 search across the knowledge vault."""
        clean_query = "".join(c if c.isalnum() or c.isspace() else " " for c in query).strip()
        if not clean_query:
            return []

        # Build FTS match expression (prefix tokens for partial matches)
        tokens = clean_query.split()
        match_expr = " ".join(f'"{t}"*' for t in tokens)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if domain:
                sql = """
                    SELECT source_domain, category, title, metadata_json, bm25(knowledge_fts) as rank
                    FROM knowledge_fts
                    WHERE knowledge_fts MATCH ? AND source_domain = ?
                    ORDER BY rank ASC
                    LIMIT ?
                """
                cursor.execute(sql, (match_expr, domain, limit))
            else:
                sql = """
                    SELECT source_domain, category, title, metadata_json, bm25(knowledge_fts) as rank
                    FROM knowledge_fts
                    WHERE knowledge_fts MATCH ?
                    ORDER BY rank ASC
                    LIMIT ?
                """
                cursor.execute(sql, (match_expr, limit))

            rows = cursor.fetchall()
            results = []
            for r in rows:
                meta = {}
                try:
                    meta = json.loads(r["metadata_json"])
                except Exception:
                    pass
                results.append({
                    "domain": r["source_domain"],
                    "category": r["category"],
                    "title": r["title"],
                    "data": meta,
                })
            return results

    # --- Domain Specific Primitives ---

    def lookup_algorithm(self, name_or_query: str) -> str:
        """Finds algorithms from TheAlgorithms with code snippets, complexity, and best-for use cases."""
        hits = self.search(name_or_query, domain="algorithms", limit=3)
        if not hits:
            # Fallback search across all domains
            hits = self.search(name_or_query, limit=2)
            if not hits:
                return f"No direct algorithmic implementation found in knowledge vault for '{name_or_query}'."

        output = [f"### 🧮 Algorithmic Blueprint: `{name_or_query}`\n"]
        for hit in hits:
            data = hit["data"]
            output.append(f"#### **{data.get('name', hit['title'])}** ({data.get('category', 'Algorithm')})")
            if "complexity" in data:
                output.append(f"• **Time/Space Complexity**: `{data['complexity']}`")
            if "summary" in data:
                output.append(f"• **Theory & Mechanism**: {data['summary']}")
            if "best_for" in data:
                output.append(f"• **Optimal Use Case**: {data['best_for']}")
            if "snippet" in data:
                output.append(f"```python\n{data['snippet']}\n```")
            output.append("")
        return "\n".join(output)

    def system_design_advisor(self, topic: str, scale_metrics: str = "") -> str:
        """Provides System Design Primer principles, tradeoffs, and back-of-the-envelope estimations."""
        hits = self.search(topic, domain="system_design", limit=3)
        if not hits:
            hits = self.search(topic, limit=2)
        
        output = [f"### 🏛️ System Design Architecture: `{topic}`\n"]
        if scale_metrics:
            output.append(f"**Target Scale/Requirements**: {scale_metrics}\n")

        for hit in hits:
            d = hit["data"]
            output.append(f"#### **{d.get('topic', hit['title'])}**")
            if "summary" in d:
                output.append(f"• **Architecture Overview**: {d['summary']}")
            if "tradeoffs" in d:
                output.append(f"• **Trade-Offs & Guarantees**: {d['tradeoffs']}")
            if "patterns" in d:
                output.append("• **Design Patterns**:")
                for pat, desc in d["patterns"].items():
                    output.append(f"  - **{pat}**: {desc}")
            if "strategies" in d:
                output.append("• **Scaling Strategies**:")
                for strat, desc in d["strategies"].items():
                    output.append(f"  - **{strat}**: {desc}")
            if "cheat_sheet" in d:
                output.append("• **Back-of-the-Envelope Estimation Metrics**:")
                for metric, val in list(d["cheat_sheet"].items())[:8]:
                    output.append(f"  - `{metric}`: {val}")
            output.append("")
        return "\n".join(output)

    def get_architecture_blueprint(self, system_type: str) -> str:
        """Returns step-by-step blueprints for building fundamental systems from scratch (Build Your Own X)."""
        hits = self.search(system_type, domain="blueprints", limit=2)
        if not hits:
            return f"No step-by-step blueprint found for '{system_type}'. Available blueprints: Git, Redis, Docker/Containers, Compilers/Interpreters, Web Servers."

        output = []
        for hit in hits:
            d = hit["data"]
            output.append(f"### 🔨 Blueprint: {d.get('system', hit['title'])}")
            output.append(f"**Domain**: {d.get('category', 'Systems Programming')}")
            output.append(f"**Core Architectural Insight**: *{d.get('key_insight', '')}*\n")
            if "core_components" in d:
                output.append(f"**Core Subsystems**: {', '.join(d['core_components'])}\n")
            if "architecture_steps" in d:
                output.append("**Implementation Stages**:")
                for step in d["architecture_steps"]:
                    output.append(f"  {step}")
            output.append("")
        return "\n".join(output)

    def find_free_developer_services(self, category: str = "", query: str = "") -> str:
        """Finds free-tier developer infrastructure (Free For Dev)."""
        search_term = f"{category} {query}".strip() or "hosting database"
        hits = self.search(search_term, domain="free_for_dev", limit=4)
        if not hits:
            hits = self.search(search_term, limit=2)

        output = [f"### ☁️ Free Developer Infrastructure: `{search_term}`\n"]
        for hit in hits:
            d = hit["data"]
            output.append(f"#### **{d.get('category', hit['title'])}**")
            for provider in d.get("providers", []):
                output.append(f"• **{provider.get('name')}**: {provider.get('free_tier')}")
            output.append("")
        return "\n".join(output)

    def find_oss_alternatives(self, proprietary_tool: str) -> str:
        """Looks up self-hosted, privacy-first open-source alternatives to commercial SaaS."""
        hits = self.search(proprietary_tool, domain="oss_alternatives", limit=3)
        if not hits:
            return f"No direct open-source alternative cataloged for '{proprietary_tool}'. Try searching for general category (e.g., 'analytics', 'database', 'search')."

        output = [f"### 🛡️ Open Source Alternatives: `{proprietary_tool}`\n"]
        for hit in hits:
            d = hit["data"]
            output.append(f"#### **{d.get('proprietary', hit['title'])}** ➔ **{d.get('oss_alternative')}**")
            output.append(f"• **Category**: {d.get('category')}")
            output.append(f"• **Tech Stack**: `{d.get('tech_stack')}`")
            output.append(f"• **Sovereignty Benefits**: {d.get('benefits')}\n")
        return "\n".join(output)

    def get_career_roadmap(self, role_or_skill: str) -> str:
        """Provides Roadmap.sh skill trees and milestone progression paths."""
        hits = self.search(role_or_skill, domain="roadmaps", limit=2)
        if not hits:
            return f"No specific roadmap found for '{role_or_skill}'. Available: AI Engineer, Backend Engineer, DevOps/SRE, System Design."

        output = []
        for hit in hits:
            d = hit["data"]
            output.append(f"### 🗺️ Developer Roadmap: **{d.get('role', hit['title'])}**\n")
            for stage in d.get("stages", []):
                topics_str = ", ".join(stage.get("topics", []))
                output.append(f"**{stage.get('stage')}**: {topics_str}")
            output.append("")
        return "\n".join(output)

    def lookup_llm_architecture(self, component: str) -> str:
        """Finds PyTorch implementations and transformer mechanics from LLMs from Scratch."""
        hits = self.search(component, domain="llm_internals", limit=2)
        if not hits:
            return f"No specific LLM architecture breakdown found for '{component}'."

        output = []
        for hit in hits:
            d = hit["data"]
            output.append(f"### 🧠 LLM Internal Architecture: {d.get('topic', hit['title'])}")
            output.append(f"• **Mechanism**: {d.get('summary')}")
            if "math" in d:
                output.append(f"• **Mathematical Formulation**: `{d['math']}`")
            if "benefits" in d:
                output.append(f"• **Operational Benefits**: {d['benefits']}")
            if "pytorch_snippet" in d:
                output.append(f"```python\n{d['pytorch_snippet']}\n```")
            output.append("")
        return "\n".join(output)

    def search_all(self, query: str, limit: int = 5) -> str:
        """General multi-domain developer knowledge search."""
        hits = self.search(query, limit=limit)
        if not hits:
            return f"No matches found across developer knowledge vault for '{query}'."

        output = [f"### 📚 Developer Knowledge Results for `{query}`:\n"]
        for idx, hit in enumerate(hits, 1):
            d = hit["data"]
            domain_label = hit["domain"].replace("_", " ").title()
            output.append(f"{idx}. **[{domain_label}] {hit['title']}** ({hit['category']})")
            if "summary" in d:
                output.append(f"   {d['summary'][:180]}...")
            elif "description" in d:
                output.append(f"   {d['description'][:180]}...")
            elif "legacy" in d:
                output.append(f"   Legacy: {d['legacy']}")
        return "\n".join(output)


# Global Singleton Instance
_ENGINE: Optional[KnowledgeEngine] = None

def get_knowledge_engine() -> KnowledgeEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = KnowledgeEngine()
    return _ENGINE
