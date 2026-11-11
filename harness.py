"""
harness.py
Plan-execute-verify helpers for the agent loop (from the "Code as Agent Harness" review, top-5 #1 and #2):

- tool_outcome(): a structured verdict per tool call (ok / error / blocked / denied, exit code, error kind,
  key error line), parsed from the strings tools.py actually returns, instead of substring guessing.
- compact(): keeps what goes back into a 4096-token prompt small: head + key error line + tail.
- ResultStore: the full text of compacted results, retrievable with the read_result tool by handle.
- CallTracker: detects dead ends (the same call with the same result, or the same error, repeating).
"""

import hashlib
import json
import os
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

DEFAULT_RESULT_CHARS = 700
_EXIT_RE = re.compile(r"^Exit code:\s*(-?\d+)\s*$", re.M)
_ERROR_KIND_RE = re.compile(r"\b([A-Z][A-Za-z]*(?:Error|Exception))\b")
_KEY_LINE_RE = re.compile(r"(Traceback|Error|Exception|error:|FAILED|File \".*\", line \d+)")


# Tools whose output is the content the user asked for get a larger share of the prompt.
_LIMIT_MULTIPLIER = {"read_workspace_file": 3, "search_vault": 2, "browse_web": 2, "search_and_extract": 2}
_SALIENT_RE = re.compile(r"error|fail|exception|traceback|warn|denied|refused|fatal|critical", re.I)


def result_char_limit(tool: str = "") -> int:
    try:
        base = max(200, int(os.getenv("ZAINE_TOOL_RESULT_CHARS", str(DEFAULT_RESULT_CHARS))))
    except ValueError:
        base = DEFAULT_RESULT_CHARS
    return base * _LIMIT_MULTIPLIER.get(tool, 1)


@dataclass
class ToolOutcome:
    status: str                    # "ok" | "error" | "blocked" | "denied"
    exit_code: Optional[int] = None
    error_kind: str = ""           # e.g. "NameError", "timeout", "not_found"
    key_line: str = ""             # the most informative error line, if any

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def fixable(self) -> bool:
        """An execution error the model can try to repair (not an approval decision or a permission)."""
        return self.status == "error"

    def label(self) -> str:
        parts = [self.status]
        if self.exit_code is not None:
            parts.append(f"exit {self.exit_code}")
        if self.error_kind:
            parts.append(self.error_kind)
        return ", ".join(parts)


def tool_outcome(result: str) -> ToolOutcome:
    text = str(result or "")
    head = text.lstrip()[:160]
    if "Security Authorization Failed" in head:
        return ToolOutcome("blocked", error_kind="approval_" + ("denied" if "Denied" in head else
                                                                 "expired" if "Expired" in head else "cancelled"))
    if "outside" in head and "permissions" in head:
        return ToolOutcome("denied", error_kind="agent_permission")

    exit_code = None
    m = _EXIT_RE.search(text)
    if m:
        exit_code = int(m.group(1))
    kind_match = _ERROR_KIND_RE.search(text)
    key = _key_line(text)
    lower_head = head.lower()
    if exit_code not in (None, 0):
        if not key:
            # No named error: the first stderr line is the most useful thing to show.
            err = text.split("Errors:\n", 1)[1] if "Errors:\n" in text else text
            key = next((ln.strip() for ln in err.splitlines() if ln.strip() and not ln.startswith("Exit code")), "")[:200]
        return ToolOutcome("error", exit_code, kind_match.group(1) if kind_match else "nonzero_exit", key)
    if lower_head.startswith(("error", "❌", "traceback")) or "timed out" in lower_head:
        kind = "timeout" if "timed out" in lower_head else (
            "not_found" if ("not found" in lower_head or "does not exist" in lower_head) else
            (kind_match.group(1) if kind_match else "tool_error"))
        return ToolOutcome("error", exit_code, kind, key or text.strip().splitlines()[0][:200] if text.strip() else "")
    if "\nErrors:\n" in text and "Traceback" in text:
        return ToolOutcome("error", exit_code, kind_match.group(1) if kind_match else "stderr", key)
    return ToolOutcome("ok", exit_code)


def _key_line(text: str) -> str:
    """Last line that names an error (Python puts the exception last), else the first matching line."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and ln.strip() not in ("Errors:", "Output:")]
    hits = [ln for ln in lines if _KEY_LINE_RE.search(ln)]
    if not hits:
        return ""
    exc = [ln for ln in hits if _ERROR_KIND_RE.search(ln)]
    return (exc[-1] if exc else hits[0])[:200]


def compact(text: str, limit: Optional[int] = None, key_line: str = "") -> Tuple[str, bool]:
    """Returns (text_for_prompt, was_compacted). Keeps the start, the end, and from the omitted middle the
    key error line plus any lines that look like errors or warnings (a small model rarely asks for more)."""
    text = str(text or "")
    limit = limit or result_char_limit()
    if len(text) <= limit:
        return text, False
    tail_len = max(120, limit // 4)
    head_len = max(120, limit // 2)
    head, tail = text[:head_len], text[-tail_len:]
    head = head[:head.rfind("\n")] if "\n" in head else head
    tail = tail[tail.find("\n") + 1:] if "\n" in tail else tail
    middle_text = text[len(head):len(text) - len(tail)]
    budget = max(0, limit - len(head) - len(tail))
    picked = []
    candidates = ([key_line] if key_line else []) + [ln.strip() for ln in middle_text.splitlines()
                                                     if _SALIENT_RE.search(ln)]
    for ln in candidates:
        ln = ln[:200]
        if ln and ln not in picked and ln in middle_text and budget - len(ln) - 3 >= 0:
            picked.append(ln)
            budget -= len(ln) + 3
    note = f"[{len(middle_text)} chars omitted of {len(text)} total"
    note += "; error/warning lines from that part:]" if picked else "; no error/warning lines in that part]"
    middle = "\n… " + note + "".join(f"\n… {ln}" for ln in picked) + "\n"
    return f"{head.rstrip()}{middle}{tail.lstrip()}", True


class ResultStore:
    """Bounded in-memory store of full tool results, addressable as R1, R2, ..."""

    def __init__(self, capacity: int = 50):
        self.capacity = capacity
        self._items: "OrderedDict[str, Tuple[str, str]]" = OrderedDict()
        self._seq = 0
        self._lock = threading.Lock()

    def put(self, tool: str, text: str) -> str:
        with self._lock:
            self._seq += 1
            rid = f"R{self._seq}"
            self._items[rid] = (tool, str(text))
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)
            return rid

    def read(self, rid: str, start: int = 0, length: int = 1500) -> str:
        rid = str(rid or "").strip().upper()
        if rid and not rid.startswith("R"):
            rid = "R" + rid
        with self._lock:
            item = self._items.get(rid)
        if item is None:
            return f"Error: no stored result '{rid}' (only the last {self.capacity} are kept)."
        tool, text = item
        start = max(0, int(start or 0))
        length = max(100, min(2000, int(length or 1500)))
        chunk = text[start:start + length]
        end = start + len(chunk)
        more = f" Next: read_result(id='{rid}', start={end})." if end < len(text) else " End of result."
        return f"[{rid} from {tool}: chars {start}-{end} of {len(text)}]\n{chunk}\n[{more.strip()}]"


@dataclass
class CallTracker:
    """Per-turn record of tool calls, to spot loops a small model falls into."""

    calls: Dict[str, int] = field(default_factory=dict)
    results: Dict[str, str] = field(default_factory=dict)
    errors: Dict[str, int] = field(default_factory=dict)

    @staticmethod
    def signature(tool: str, args) -> str:
        try:
            blob = json.dumps(args, sort_keys=True, default=str)
        except Exception:
            blob = str(args)
        return f"{tool}:{blob}"

    def record(self, tool: str, args, result: str, outcome: ToolOutcome) -> List[str]:
        """Returns warnings for the model when a call or an error repeats."""
        warnings = []
        sig = self.signature(tool, args)
        digest = hashlib.sha1(str(result).encode("utf-8", "replace")).hexdigest()
        seen = self.calls.get(sig, 0)
        if seen and self.results.get(sig) == digest:
            warnings.append(f"You already called {tool} with these exact arguments and got the same result. "
                            f"Do not repeat it; use the result or try a different approach.")
        self.calls[sig] = seen + 1
        self.results[sig] = digest
        if outcome.status == "error" and outcome.key_line:
            ekey = f"{tool}:{outcome.key_line}"
            self.errors[ekey] = self.errors.get(ekey, 0) + 1
            if self.errors[ekey] == 2:
                warnings.append(f"The same error happened twice ({outcome.key_line}). Change the approach "
                                f"instead of retrying the same fix.")
        return warnings

    def stuck(self) -> bool:
        """True once any identical call ran 3 times or any identical error happened 3 times."""
        return any(n >= 3 for n in self.calls.values()) or any(n >= 3 for n in self.errors.values())
