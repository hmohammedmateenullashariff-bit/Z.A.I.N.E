"""
autonomy/memory_bridge.py
Step-relevant, privacy-aware memory retrieval bounded strictly within ~2000 characters.

Reuses:
- obsidian_adapter.SEARCH_STOPWORDS
- memory_manager.MemoryManager & MemoryPolicy
- memory.get_all_memories / retrieve_relevant_learnings
- autonomy.privacy.mark_session_private
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from autonomy.privacy import mark_session_private
from memory_types import PrivacyTaint, TrustLevel

MAX_MEMORY_BUDGET_CHARS = 2000

_EXTRA_STEP_STOPWORDS = frozenset(
    {
        "step",
        "using",
        "create",
        "write",
        "edit",
        "update",
        "run",
        "check",
        "verify",
        "report",
        "done",
        "file",
        "files",
        "tool",
        "call",
        "then",
        "next",
        "please",
    }
)


def extract_step_keywords(current_step: str, goal: str = "", *, max_terms: int = 8) -> List[str]:
    """
    Extracts salient keywords prioritized by the active step (with goal fallback only when
    the step description has fewer than 3 concrete terms).
    """
    try:
        from obsidian_adapter import SEARCH_STOPWORDS
    except Exception:
        SEARCH_STOPWORDS = set()

    stopwords = set(SEARCH_STOPWORDS) | _EXTRA_STEP_STOPWORDS

    def _tokens(text: str) -> List[str]:
        found = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", (text or "").lower())
        seen = set()
        out = []
        for tok in found:
            if tok in stopwords or tok.isdigit():
                continue
            if tok not in seen:
                seen.add(tok)
                out.append(tok)
        return out

    step_terms = _tokens(current_step)
    if len(step_terms) >= 3 or not goal:
        return step_terms[:max_terms]

    merged = list(step_terms)
    for gt in _tokens(goal):
        if gt not in merged:
            merged.append(gt)
        if len(merged) >= max_terms:
            break
    return merged[:max_terms]


def retrieve_step_memory(
    goal: str,
    current_step: str = "",
    *,
    max_chars: int = MAX_MEMORY_BUDGET_CHARS,
    vault_path: Optional[str] = None,
    mark_taint: bool = True,
    include_sqlite: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """
    Retrieves ONLY memory items relevant to `current_step` (or `goal` if step is brief),
    respecting the ~2000-character context budget and tagging session privacy taint.
    """
    budget = max(120, min(int(max_chars or MAX_MEMORY_BUDGET_CHARS), MAX_MEMORY_BUDGET_CHARS))
    keywords = extract_step_keywords(current_step, goal)
    if not keywords:
        return "", {"count": 0, "chars": 0, "taint": "CLEAN", "keywords": []}

    query_str = " ".join(keywords)
    lines: List[str] = []
    tainted_local = False

    # 1. Durable Obsidian vault memories (primary source)
    try:
        from memory_manager import MemoryManager, MemoryPolicy, get_memory_manager

        mm = MemoryManager(vault_path=vault_path) if vault_path else get_memory_manager()
        if mm.available:
            entries = mm.search(query=query_str, limit=6)
            for entry in entries:
                if entry.trust in (TrustLevel.UNTRUSTED, TrustLevel.REJECTED):
                    continue
                if not MemoryPolicy.validate_retrieval(entry):
                    continue
                taint_val = getattr(entry, "privacy_taint", PrivacyTaint.LOCAL_ONLY.value)
                if str(taint_val).upper() == PrivacyTaint.LOCAL_ONLY.value:
                    tainted_local = True
                    if mark_taint:
                        mark_session_private(f"vault:{entry.id}", PrivacyTaint.LOCAL_ONLY.value)
                lines.append(entry.format_for_context(include_trust=True, include_privacy=True))
    except Exception:
        pass

    # 2. Step-relevant SQLite memories & task learnings (never dump unrelated entries)
    if include_sqlite:
        try:
            from memory import get_all_memories_with_taint, retrieve_relevant_learnings
            from memory_manager import MemoryPolicy

            scored_facts: List[Tuple[int, str, str, str]] = []
            for key, info in get_all_memories_with_taint().items():
                val = str(info.get("value") or "")
                priv = str(info.get("privacy_taint") or PrivacyTaint.LOCAL_ONLY.value)
                hay = f"{key} {val}".lower()
                hits = sum(1 for kw in keywords if kw in hay)
                if hits > 0:
                    safe, _ = MemoryPolicy.check_safe_text(f"{key} {val}")
                    if safe:
                        scored_facts.append((hits, key, val, priv))
            scored_facts.sort(key=lambda x: x[0], reverse=True)

            for _hits, key, val, priv in scored_facts[:4]:
                if priv.upper() == PrivacyTaint.LOCAL_ONLY.value:
                    tainted_local = True
                    if mark_taint:
                        mark_session_private(f"sqlite:{key}", PrivacyTaint.LOCAL_ONLY.value)
                lines.append(f"- [fact] [{priv}] {key}: {val}")

            for lesson in retrieve_relevant_learnings(query_str, limit=2):
                safe, _ = MemoryPolicy.check_safe_text(str(lesson))
                if not safe:
                    continue
                tainted_local = True
                if mark_taint:
                    mark_session_private("sqlite:task_learnings", PrivacyTaint.LOCAL_ONLY.value)
                lines.append(f"- [lesson] [LOCAL_ONLY] {str(lesson).strip()}")
        except Exception:
            pass

    if not lines:
        return "", {"count": 0, "chars": 0, "taint": "CLEAN", "keywords": keywords}

    header_taint = PrivacyTaint.LOCAL_ONLY.value if tainted_local else PrivacyTaint.SHAREABLE.value
    prefix = f'<step_memory privacy="{header_taint}">\n'
    suffix = "\n</step_memory>"
    allowed_inner = max(0, budget - len(prefix) - len(suffix))

    selected: List[str] = []
    used = 0
    for ln in lines:
        add_len = len(ln) + (1 if selected else 0)
        if used + add_len <= allowed_inner:
            selected.append(ln)
            used += add_len
        elif not selected and allowed_inner > 20:
            selected.append(ln[: max(0, allowed_inner - 3)].rstrip() + "...")
            used = len(selected[-1])
            break
        else:
            break

    if not selected:
        return "", {"count": 0, "chars": 0, "taint": header_taint, "keywords": keywords}

    block = f"{prefix}" + "\n".join(selected) + f"{suffix}"
    return block[:budget], {
        "count": len(selected),
        "chars": len(block[:budget]),
        "taint": header_taint,
        "keywords": keywords,
    }

