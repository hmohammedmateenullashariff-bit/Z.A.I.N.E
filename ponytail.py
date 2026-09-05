"""
Z.A.I.N.E — Ponytail Architectural Thinking Engine
Based on the Ponytail Framework by Dietrich Gebert.
Core Philosophy: "The best code is the code you never wrote."

Forces Zaine's specialized coding model (Qwen2.5-Coder) to think before writing code,
preventing over-engineering, bloat, and premature abstractions by sequentially
climbing the 7-Rung Ponytail Decision Ladder.
"""

import re
import requests

PONYTAIL_DECISION_LADDER = """1. Rung 1 (YAGNI — You Aren't Gonna Need It):
   - What speculative features, premature abstractions, or boilerplate can be dropped?
   - Solve only the immediate concrete problem. Do not build frameworks for hypothetical futures.

2. Rung 2 (Already in this Codebase?):
   - Check if an existing function, helper, or pattern in the project can be reused.
   - Never write duplicate utility logic.

3. Rung 3 (Does the Standard Library solve it?):
   - Prefer Python's rich built-in standard library over custom wheels:
     (e.g., pathlib, dataclasses, itertools, functools, collections, concurrent.futures, json, sqlite3, bisect, heapq).

4. Rung 4 (Native Platform / Runtime Feature?):
   - Can the OS, shell, or runtime platform handle this directly?

5. Rung 5 (Already Installed Dependency?):
   - Does an already installed package in the environment handle this cleanly?

6. Rung 6 (Can it be simple and concise?):
   - Avoid deep inheritance trees, abstract factories, and ceremonial wrapper classes.
   - A single clean function or dataclass is almost always better than a multi-tier hierarchy.

7. Rung 7 (Only Then: Write the Minimal Robust Code):
   - Emit the cleanest, most efficient, production-grade implementation that works.
   - Safety First: Never compromise input validation, error handling, security boundaries, or crash safety for brevity."""

PONYTAIL_SYSTEM_PROMPT = f"""You are an elite software architect practicing Ponytail Engineering.
Your core principle: "The best code is the code you never wrote."
You despise over-engineering, code bloat, and premature abstractions.

CRITICAL INSTRUCTION:
Before emitting ANY code, you MUST FIRST THINK and deliberate inside a <thinking>...</thinking> block by explicitly climbing the 7-Rung Ponytail Decision Ladder:

{PONYTAIL_DECISION_LADDER}

Format your output strictly as:
<thinking>
1. Rung 1 (YAGNI): [Your evaluation]
2. Rung 2 (Reuse): [Your evaluation]
3. Rung 3 (Stdlib): [Your evaluation]
4. Rung 4 (Native): [Your evaluation]
5. Rung 5 (Dependencies): [Your evaluation]
6. Rung 6 (Simplicity): [Your evaluation]
7. Rung 7 (Minimal Architecture Plan): [Minimal plan]
</thinking>

```python
[Your clean, minimal, production-grade implementation]
```
"""


def format_ponytail_user_prompt(prompt: str, context_code: str = "") -> str:
    """Formats the user request and existing context for Ponytail deliberation."""
    msg = f"Task / Code Request:\n{prompt.strip()}\n"
    if context_code and context_code.strip():
        msg += f"\nExisting Codebase Context / File Content:\n```python\n{context_code.strip()}\n```\n"
    return msg


def extract_ponytail_thinking(response_text: str) -> tuple[str, str]:
    """
    Extracts the <thinking>...</thinking> reasoning block and the code implementation.
    Returns (thinking_text, clean_code_or_full_response).
    """
    thinking = ""
    thinking_match = re.search(r"<thinking>(.*?)</thinking>", response_text, re.DOTALL | re.IGNORECASE)
    if thinking_match:
        thinking = thinking_match.group(1).strip()
        cleaned_body = re.sub(r"<thinking>.*?</thinking>", "", response_text, flags=re.DOTALL | re.IGNORECASE).strip()
    else:
        # Fallback: check for explicit Rung references
        if "Rung 1" in response_text and "```" in response_text:
            parts = response_text.split("```", 1)
            thinking = parts[0].strip()
            cleaned_body = "```" + parts[1].strip()
        else:
            cleaned_body = response_text.strip()

    return thinking, cleaned_body


def run_ponytail_coder(
    prompt: str,
    context_code: str = "",
    model: str = "qwen2.5-coder:3b",
    timeout: int = 120,
) -> dict:
    """
    Runs the local coding model with Ponytail pre-thinking enabled.
    Returns:
      {
        "thinking": str,
        "code": str,
        "full_text": str,
        "model": str,
        "status": "ok" | "error"
      }
    """
    user_content = format_ponytail_user_prompt(prompt, context_code)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": PONYTAIL_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 2048,
        },
    }

    try:
        resp = requests.post("http://localhost:11434/api/chat", json=payload, timeout=timeout)
        if resp.status_code == 200:
            content = resp.json().get("message", {}).get("content", "").strip()
            thinking, code = extract_ponytail_thinking(content)
            return {
                "thinking": thinking,
                "code": code,
                "full_text": content,
                "model": model,
                "status": "ok",
            }
        else:
            return {
                "thinking": "",
                "code": f"Error from coder engine ({resp.status_code}): {resp.text}",
                "full_text": "",
                "model": model,
                "status": "error",
            }
    except Exception as e:
        return {
            "thinking": "",
            "code": f"Ponytail coder connection error: {e}",
            "full_text": "",
            "model": model,
            "status": "error",
        }


def format_ponytail_output(thinking: str, code: str, include_thinking: bool = True) -> str:
    """Formats the final output for presentation to the user or agent."""
    if not thinking or not include_thinking:
        return code

    formatted = f"💡 [PONYTAIL ARCHITECTURAL DELIBERATION]:\n{thinking}\n\n{code}"
    return formatted
