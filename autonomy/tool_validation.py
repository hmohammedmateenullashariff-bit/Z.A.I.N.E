"""
autonomy/tool_validation.py
Local-model (7B) tool-call validation with single deterministic repair pass.

Flow enforced by AutonomousLoop:
  1. Inspect output: if not a JSON / tool-call attempt -> "plain_text".
  2. Strict parse & schema check -> "ok" if valid {"tool": str, "args": dict}.
  3. Deterministic repair ONCE -> "repaired" if valid JSON object(s) recovered.
  4. Otherwise -> "needs_retry" so the loop retries the model AT MOST ONCE
     and fails cleanly if still invalid (no infinite repair loops).
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


_TOOL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]{0,63}$")
_TOOL_MARKER_RE = re.compile(
    r'(\[TOOL\]|```(?:json)?|"(?:tool|tool_name|name|function|action)"\s*:|\'(?:tool|tool_name|name|function|action)\'\s*:)',
    re.IGNORECASE,
)


@dataclass
class ToolValidationResult:
    """Outcome of strict validation + single deterministic repair."""

    status: str  # "plain_text" | "ok" | "repaired" | "needs_retry"
    calls: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    repair_notes: str = ""


def looks_like_tool_attempt(text: str) -> bool:
    """Returns True when model text appears to attempt a JSON or [TOOL] call."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    if stripped.startswith("{") or stripped.startswith("[{"):
        return True
    if _TOOL_MARKER_RE.search(stripped):
        return True
    if stripped.startswith("```") and "{" in stripped:
        return True
    return False


def _normalize_call_obj(obj: Any, *, allow_string_args: bool = False) -> Tuple[Optional[Dict[str, Any]], str]:
    """Normalizes supported dict shapes into {"tool": str, "args": dict}."""
    if not isinstance(obj, dict):
        return None, "Tool call object must be a JSON object."

    # Non-tool structured answers such as {"final_answer": "..."} are NOT malformed calls;
    # caller checks keys before normalizing, or returns error if wrong shape.
    tname: Optional[str] = None
    raw_args: Any = None
    has_explicit_args = False

    if "tool" in obj:
        raw_t = obj.get("tool")
        if not isinstance(raw_t, str) or not raw_t.strip():
            return None, "Field 'tool' must be a non-empty string."
        tname = raw_t.strip()
        for k in ("args", "parameters", "arguments", "input"):
            if k in obj:
                raw_args = obj[k]
                has_explicit_args = True
                break
    elif "function" in obj and isinstance(obj["function"], dict):
        fn = obj["function"]
        raw_t = fn.get("name")
        if not isinstance(raw_t, str) or not raw_t.strip():
            return None, "Nested 'function.name' must be a non-empty string."
        tname = raw_t.strip()
        for k in ("arguments", "parameters", "args"):
            if k in fn:
                raw_args = fn[k]
                has_explicit_args = True
                break
    else:
        for name_k in ("name", "function", "action", "tool_name"):
            if name_k in obj:
                raw_t = obj.get(name_k)
                if not isinstance(raw_t, str) or not raw_t.strip():
                    return None, f"Field '{name_k}' must be a non-empty string."
                tname = raw_t.strip()
                for k in ("arguments", "parameters", "args", "action_input"):
                    if k in obj:
                        raw_args = obj[k]
                        has_explicit_args = True
                        break
                break

    if not tname:
        return None, "Missing 'tool' name in JSON object."
    if not _TOOL_NAME_RE.match(tname):
        return None, f"Invalid tool identifier '{tname}'."

    if not has_explicit_args or raw_args is None:
        args_dict: Dict[str, Any] = {}
    elif isinstance(raw_args, dict):
        args_dict = raw_args
    elif allow_string_args and isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
            if not isinstance(parsed, dict):
                return None, "Parsed string 'args' must be a JSON object."
            args_dict = parsed
        except Exception as exc:
            return None, f"Could not parse stringified 'args': {exc}"
    else:
        return None, f"Field 'args' must be a JSON object, got {type(raw_args).__name__}."

    return {"tool": tname, "args": args_dict}, ""


def _extract_strict_json_objects(text: str) -> Tuple[List[Any], str]:
    """Extracts strict JSON objects via json.JSONDecoder(strict=True)."""
    decoder = json.JSONDecoder(strict=True)
    objs: List[Any] = []
    last_err = "No valid JSON object found."
    idx = 0
    n = len(text)
    while idx < n:
        start = text.find("{", idx)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
            objs.append(obj)
            idx = max(end, start + 1)
        except json.JSONDecodeError as exc:
            last_err = f"JSON syntax error at pos {exc.pos}: {exc.msg}"
            # Advance past this brace only after recording the error so unbalanced JSON fails cleanly.
            break
    return objs, last_err


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, flags=re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def _repair_json_text_once(text: str) -> Tuple[str, str]:
    """Applies one deterministic pass of structural repairs to malformed JSON text."""
    notes: List[str] = []
    repaired = _strip_code_fences(text)
    if repaired != text.strip():
        notes.append("stripped_fences")

    # Normalize curly/smart quotes sometimes emitted by quantized models
    norm_quotes = (
        repaired.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    if norm_quotes != repaired:
        repaired = norm_quotes
        notes.append("normalized_quotes")

    # Handle [TOOL] <name>, {json} syntax cleanly
    pseudo = re.match(r"^\s*\[TOOL\]\s*[\"']?([A-Za-z_][A-Za-z0-9_.:-]*)[\"']?(?:\s*,\s*|\s+)?([\s\S]*)$", repaired)
    if pseudo:
        tname = pseudo.group(1).strip()
        rest = pseudo.group(2).strip()
        if not rest:
            repaired = json.dumps({"tool": tname, "args": {}})
            notes.append("converted_pseudo_tool")
        elif rest.startswith("{"):
            try:
                parsed_rest = json.loads(rest)
                if isinstance(parsed_rest, dict):
                    if "tool" in parsed_rest:
                        repaired = json.dumps(parsed_rest)
                    elif "args" in parsed_rest and isinstance(parsed_rest["args"], dict) and len(parsed_rest) == 1:
                        repaired = json.dumps({"tool": tname, "args": parsed_rest["args"]})
                    else:
                        repaired = json.dumps({"tool": tname, "args": parsed_rest})
                    notes.append("converted_pseudo_tool")
            except Exception:
                repaired = f'{{"tool": {json.dumps(tname)}, "args": {rest}}}'
                notes.append("wrapped_pseudo_tool")

    # Remove trailing commas before } or ] (safe first pass)
    no_trailing = re.sub(r",\s*([}\]])", r"\1", repaired)
    if no_trailing != repaired:
        repaired = no_trailing
        notes.append("removed_trailing_commas")

    # Trim leading non-JSON chatter up to first '{'
    first_brace = repaired.find("{")
    if first_brace > 0:
        repaired = repaired[first_brace:]
        notes.append("trimmed_prefix")

    # Only quote bare keys / close braces if strict parse still fails
    objs_pre, _ = _extract_strict_json_objects(repaired)
    if objs_pre:
        return repaired, ",".join(notes)

    quoted_keys = re.sub(r'([{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', repaired)
    if quoted_keys != repaired:
        repaired = quoted_keys
        notes.append("quoted_keys")

    # Balance up to 3 missing closing braces if truncated cleanly
    open_curly = repaired.count("{") - repaired.count("}")
    if 0 < open_curly <= 3:
        repaired = repaired + ("}" * open_curly)
        notes.append(f"closed_{open_curly}_braces")

    return repaired, ",".join(notes)


def validate_and_repair_tool_calls(
    text: str,
    *,
    strict_only: bool = False,
) -> ToolValidationResult:
    """
    Validates model output for tool calls.

    If `text` does not look like a tool/JSON attempt -> returns status='plain_text'.
    First checks strict JSON; if malformed and `not strict_only`, runs one
    deterministic repair pass; if still invalid -> returns status='needs_retry'.
    """
    if not looks_like_tool_attempt(text):
        return ToolValidationResult(status="plain_text")

    stripped = (text or "").strip()

    # 1. Strict JSON check on unwrapped text (only if text starts neatly with '{' or contains clean JSON)
    candidate_strict = stripped
    if candidate_strict.startswith("{"):
        objs, err = _extract_strict_json_objects(candidate_strict)
        if objs:
            valid_calls: List[Dict[str, Any]] = []
            norm_err = ""
            # Ensure tail isn't broken unparsed '{' or trailing non-JSON garbage
            decoder = json.JSONDecoder(strict=True)
            pos = 0
            trailing_broken = False
            while pos < len(candidate_strict):
                s = candidate_strict.find("{", pos)
                if s == -1:
                    if candidate_strict[pos:].strip():
                        trailing_broken = True
                        err = "Trailing non-JSON text outside tool-call object."
                    break
                if candidate_strict[pos:s].strip():
                    trailing_broken = True
                    err = "Non-JSON text between tool-call objects."
                    break
                try:
                    _obj, end = decoder.raw_decode(candidate_strict, s)
                    pos = max(end, s + 1)
                except json.JSONDecodeError as exc:
                    trailing_broken = True
                    err = f"JSON syntax error at pos {exc.pos}: {exc.msg}"
                    break
            if not trailing_broken:
                for obj in objs:
                    call, perr = _normalize_call_obj(obj, allow_string_args=False)
                    if call is None:
                        norm_err = perr
                        valid_calls = []
                        break
                    valid_calls.append(call)
                if valid_calls:
                    return ToolValidationResult(status="ok", calls=valid_calls)
            err = norm_err or err
    else:
        err = "Tool output is not raw strict JSON."

    if strict_only:
        return ToolValidationResult(status="needs_retry", error=err)

    # 2. Single deterministic repair pass
    repaired_text, notes = _repair_json_text_once(stripped)
    objs, rep_err = _extract_strict_json_objects(repaired_text)

    # Fallback inside single repair pass: Python literal dict syntax (single quotes / True / None)
    if not objs:
        start = repaired_text.find("{")
        end = repaired_text.rfind("}")
        if start != -1 and end > start:
            try:
                lit_obj = ast.literal_eval(repaired_text[start : end + 1])
                if isinstance(lit_obj, dict):
                    objs = [lit_obj]
                    notes = (notes + ",ast_literal").strip(",")
            except Exception as exc:
                rep_err = f"{rep_err}; ast_literal failed: {exc}"

    if objs:
        repaired_calls: List[Dict[str, Any]] = []
        norm_err = ""
        for obj in objs:
            call, perr = _normalize_call_obj(obj, allow_string_args=True)
            if call is None:
                norm_err = perr
                repaired_calls = []
                break
            repaired_calls.append(call)
        if repaired_calls:
            return ToolValidationResult(
                status="repaired",
                calls=repaired_calls,
                repair_notes=notes or "structural_repair",
            )
        rep_err = norm_err or rep_err

    return ToolValidationResult(
        status="needs_retry",
        error=rep_err or err or "Unable to parse valid tool-call JSON.",
        repair_notes=notes,
    )
