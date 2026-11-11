"""
autonomy/sandbox.py
Workspace sandbox enforcement, traversal/NTFS hardening, read-only outside-workspace
access, approval-gated external writes, and unified diff previews before overwrites.

Reuses:
- edith.ast_security_gate.ZONE_0_KERNEL_FILES & scan_code_ast
- approval.get_approval_listener
"""

from __future__ import annotations

import difflib
import os
from pathlib import Path
from typing import Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LIVE_VAULT_PATH = Path(r"D:\Z.A.I.N.E vault\Z.A.I.N.E")

_SENSITIVE_DIR_NAMES = frozenset({".git", ".venv", "python-packages", "models", ".ssh"})
_PROTECTED_RUNTIME_FILES = frozenset(
    {
        "agent.py",
        "tools.py",
        "toolmaker.py",
        "agents/profiles.json",
        "autonomy/guards.py",
        "autonomy/sandbox.py",
        "autonomy/untrusted.py",
        "autonomy/loop.py",
        "autonomy/subagents.py",
    }
)


def _strip_quotes_and_check_control(raw_path: str) -> str:
    if not isinstance(raw_path, str):
        raise ValueError("Access denied: path must be a string.")
    clean = raw_path
    if len(clean) >= 2 and ((clean[0] == clean[-1] == '"') or (clean[0] == clean[-1] == "'")):
        clean = clean[1:-1]
    if not clean or not clean.strip():
        raise ValueError("Access denied: path cannot be empty.")
    for ch in clean:
        if ord(ch) < 32:
            raise ValueError("Access denied: control characters and NUL bytes are not allowed in paths.")
    return clean


def _validate_segments(parts: Tuple[str, ...], raw_display: str) -> None:
    for seg in parts:
        if not seg:
            continue
        if seg == "..":
            raise ValueError(f"Access denied: path traversal '..' blocked in '{raw_display}'.")
        if "~" in seg:
            raise ValueError(f"Access denied: Windows 8.3 short-name segment '~' blocked in '{raw_display}'.")
        if seg not in (".",) and (seg.endswith(".") or seg != seg.strip()):
            raise ValueError(f"Access denied: trailing dot or whitespace blocked in '{raw_display}'.")


def _validate_raw_path(raw_path: str, *, allow_drive_prefix: bool) -> str:
    clean = _strip_quotes_and_check_control(raw_path)

    if clean.startswith(("\\\\?\\", "\\\\.\\", "//?/", "//./")):
        raise ValueError(f"Access denied: extended device path prefix blocked in '{raw_path}'.")
    if clean.startswith(("\\\\", "//")):
        raise ValueError(f"Access denied: UNC network paths are blocked in '{raw_path}'.")

    # Block NTFS Alternate Data Streams (:) and drive-relative paths (C:foo)
    colon_idx = clean.find(":")
    if colon_idx != -1:
        is_valid_drive = (
            allow_drive_prefix
            and colon_idx == 1
            and clean[0].isascii()
            and clean[0].isalpha()
            and len(clean) >= 3
            and clean[2] in ("\\", "/")
            and ":" not in clean[2:]
        )
        if not is_valid_drive:
            raise ValueError(f"Access denied: NTFS alternate data streams or colon syntax blocked in '{raw_path}'.")

    return clean


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junc = getattr(os.path, "isjunction", None)
    if is_junc is not None:
        try:
            return bool(is_junc(path))
        except OSError:
            return False
    return False


def _verify_descendant_within_root(root_unres: Path, root_real: Path, rel_path: Path, raw_display: str) -> Path:
    current = root_unres
    for seg in rel_path.parts:
        if seg in ("", "."):
            continue
        current = current / seg
        if _is_link_or_junction(current):
            try:
                resolved_step = current.resolve()
                resolved_step.relative_to(root_real)
            except Exception:
                raise ValueError(
                    f"Access denied: '{raw_display}' traverses a symlink or junction outside workspace."
                )
            try:
                raw_target = os.readlink(current)
                for pfx in ("\\\\?\\", "\\??\\"):
                    if raw_target.startswith(pfx):
                        raw_target = raw_target[len(pfx):]
                raw_link = Path(raw_target)
                link_abs = (
                    (current.parent / raw_link).resolve()
                    if not raw_link.is_absolute()
                    else raw_link.resolve()
                )
                link_abs.relative_to(root_real)
            except ValueError:
                raise ValueError(
                    f"Access denied: '{raw_display}' links outside the workspace sandbox."
                )
            except OSError:
                pass
        elif current.exists():
            try:
                current.resolve().relative_to(root_real)
            except ValueError:
                raise ValueError(f"Access denied: '{raw_display}' escapes the workspace sandbox.")

    resolved = (root_unres / rel_path).resolve()
    try:
        resolved.relative_to(root_real)
    except ValueError:
        raise ValueError(f"Access denied: '{raw_display}' attempts to leave the workspace sandbox.")
    return resolved


def resolve_sandbox_path(filepath: str, workspace_dir: Optional[Path] = None) -> Path:
    """
    Safely resolves `filepath` strictly inside `workspace_dir` (or ZAINE_WORKSPACE / ./workspace),
    blocking traversal ('..'), NTFS ADS (':'), 8.3 short names ('~'), extended prefixes,
    trailing dots/spaces, and symlink/junction escapes.
    """
    if workspace_dir is None:
        env_ws = os.getenv("ZAINE_WORKSPACE", "").strip()
        ws_unres = Path(env_ws) if env_ws else (PROJECT_ROOT / "workspace")
        ws_unres.mkdir(parents=True, exist_ok=True)
    else:
        ws_unres = Path(workspace_dir)
    ws_real = ws_unres.resolve()

    clean = _validate_raw_path(filepath, allow_drive_prefix=True)
    # Normalize slashes for uniform segment inspection
    norm = clean.replace("\\", "/")
    cand = Path(norm)

    if cand.is_absolute():
        # Block explicit '..' components before resolving
        _validate_segments(tuple(p for p in norm.split("/") if p and not (len(p) == 2 and p[1] == ":")), filepath)
        try:
            cand_real = cand.resolve()
            rel_inside = cand_real.relative_to(ws_real)
        except ValueError:
            raise ValueError(f"Access denied: '{filepath}' attempts to leave the workspace sandbox.")
        return _verify_descendant_within_root(ws_unres, ws_real, rel_inside, filepath)

    raw_parts = tuple(p for p in norm.split("/") if p)
    _validate_segments(raw_parts, filepath)

    # Strip one legacy leading "./", "workspace/", or "<ws_name>/" prefix only after validating segments
    if raw_parts and raw_parts[0] == ".":
        raw_parts = raw_parts[1:]
    ws_name_low = ws_unres.name.lower()
    if raw_parts and raw_parts[0].lower() in ("workspace", ws_name_low):
        raw_parts = raw_parts[1:]
    norm = "/".join(raw_parts) or "."

    return _verify_descendant_within_root(ws_unres, ws_real, Path(norm), filepath)


def resolve_external_path(filepath: str, *, default_base: Optional[Path] = None) -> Path:
    """
    Resolves a path outside the workspace for read-only inspection or approval-gated edits.
    Strictly blocks '..', NTFS ADS (':'), 8.3 short names ('~'), UNC/device prefixes, and trailing dots.
    """
    clean = _validate_raw_path(filepath, allow_drive_prefix=True)
    norm = clean.replace("\\", "/")
    parts = [p for p in norm.split("/") if p]
    if parts and len(parts[0]) == 2 and parts[0][1] == ":":
        check_parts = tuple(parts[1:])
    else:
        check_parts = tuple(parts)
    _validate_segments(check_parts, filepath)

    p = Path(clean)
    if p.is_absolute():
        return p.resolve()
    base = (default_base or PROJECT_ROOT).resolve()
    return (base / p).resolve()


def _rel_to_project(path: Path) -> Optional[str]:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return None


def is_sensitive_path(path: Path) -> bool:
    """Returns True for secrets, credentials, tokens, DBs, git internals, venvs, and the live vault."""
    try:
        resolved = path.resolve()
    except OSError:
        return True

    low_parts = [p.lower() for p in resolved.parts]
    if any(d in low_parts for d in _SENSITIVE_DIR_NAMES):
        return True

    name_low = resolved.name.lower()
    if name_low == ".env" or name_low.startswith(".env.") or name_low == ".zaine_core.json":
        return True
    if name_low.endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    if name_low.endswith(".json") and any(
        k in name_low for k in ("token", "secret", "credential", "client_secret", "oauth")
    ):
        return True
    if "face_id" in name_low or "zaine_face_id" in "/".join(low_parts):
        return True

    rel = _rel_to_project(resolved)
    if rel is not None:
        rel_low = rel.lower()
        if rel_low == "data" or rel_low.startswith("data/"):
            return True

    # Always protect the real production Obsidian vault from direct autonomous tampering
    try:
        live_real = LIVE_VAULT_PATH.resolve()
        if resolved == live_real or live_real in resolved.parents:
            return True
    except Exception:
        pass

    return False


def is_write_blocked_path(path: Path) -> Optional[str]:
    """
    Returns a denial reason if `path` may NEVER be modified by an autonomous agent
    (Zone 0 kernel files, secrets, live vault, core autonomy safeguards), else None.
    """
    if is_sensitive_path(path):
        return f"Access denied: '{path}' is a protected sensitive/credential/system path."

    rel = _rel_to_project(path)
    if rel is None:
        return None

    try:
        from edith.ast_security_gate import ZONE_0_KERNEL_FILES
    except Exception:
        ZONE_0_KERNEL_FILES = set()

    rel_norm = rel.replace("\\", "/")
    if rel_norm in ZONE_0_KERNEL_FILES or path.name in ZONE_0_KERNEL_FILES:
        return f"Access denied: '{rel_norm}' is a locked Zone 0 kernel file."

    if rel_norm in _PROTECTED_RUNTIME_FILES:
        return f"Access denied: '{rel_norm}' is a protected Z.A.I.N.E agent runtime module."

    return None


def compute_unified_diff(target_display: str, old_text: str, new_text: str, *, max_lines: int = 120) -> str:
    """Computes a bounded unified diff between `old_text` and `new_text`."""
    old_norm = old_text.replace("\r\n", "\n")
    new_norm = new_text.replace("\r\n", "\n")
    if old_norm == new_norm:
        return ""
    diff_lines = list(
        difflib.unified_diff(
            old_norm.splitlines(keepends=True),
            new_norm.splitlines(keepends=True),
            fromfile=f"a/{target_display}",
            tofile=f"b/{target_display}",
            n=3,
        )
    )
    if not diff_lines:
        return ""
    if len(diff_lines) > max_lines:
        omitted = len(diff_lines) - max_lines
        diff_lines = diff_lines[:max_lines] + [f"\n... ({omitted} more diff lines truncated)\n"]
    return "".join(diff_lines).rstrip("\r\n")


def emit_diff_preview(tool_name: str, filepath: str, diff_text: str, *, is_overwrite: bool = True) -> None:
    """Forwards a unified diff preview to the active SSE/approval stream before modifying disk."""
    if not diff_text:
        return
    try:
        from approval import get_approval_listener

        listener = get_approval_listener()
        if listener is not None:
            listener(
                "diff_preview",
                tool_name,
                {
                    "filepath": str(filepath),
                    "is_overwrite": bool(is_overwrite),
                    "diff": diff_text[:3500],
                },
            )
    except Exception:
        pass


def read_outside_workspace(filepath: str, *, workspace_dir: Optional[Path] = None, max_chars: int = 16000) -> str:
    """
    Read-only access to non-sensitive files outside the workspace.
    Blocks traversal ('..'), NTFS anomalies, binary blobs, and credential/secret paths.
    """
    try:
        target = resolve_external_path(filepath)
    except ValueError as exc:
        return f"Error reading external file '{filepath}': {exc}"

    if is_sensitive_path(target):
        return f"Error: Access denied — '{filepath}' is a protected sensitive or credential path."
    if not target.exists():
        return f"Error: External file '{filepath}' does not exist."
    if not target.is_file():
        return f"Error: '{filepath}' is not a regular file."

    try:
        raw = target.read_bytes()
    except Exception as exc:
        return f"Error reading external file '{filepath}': {exc}"

    if b"\x00" in raw[:4096]:
        return f"Error: '{filepath}' appears to be a binary file and cannot be read as text."

    text = raw.decode("utf-8", errors="replace")
    truncated_note = ""
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated_note = f"\n... [truncated to {max_chars} chars]"

    return f"[READ-ONLY OUTSIDE WORKSPACE: {target}]\n{text}{truncated_note}"


def precheck_external_write(
    filepath: str,
    content: str = "",
) -> Tuple[Optional[Path], str, bool, Optional[str]]:
    """
    Validates an external write BEFORE any approval prompt or write:
    checks path safety, Zone 0/sensitive blocks, optional Python AST gate, and computes diff.
    Returns (resolved_path, diff_text, is_overwrite, block_error_or_None).
    """
    try:
        target = resolve_external_path(filepath)
    except ValueError as exc:
        return None, "", False, f"Error writing external file '{filepath}': {exc}"

    block_reason = is_write_blocked_path(target)
    if block_reason:
        return None, "", False, f"Error: {block_reason}"

    if target.exists() and target.is_dir():
        return None, "", False, f"Error: '{filepath}' is a directory."

    # Enforce AST safety scan when writing Python inside PROJECT_ROOT
    rel = _rel_to_project(target)
    if rel is not None and target.suffix.lower() == ".py" and content:
        try:
            from edith.ast_security_gate import SecurityVerdict, scan_code_ast

            scan = scan_code_ast(content, target_zone=1, file_path=str(target))
            if scan.verdict == SecurityVerdict.CRITICAL_BLOCK:
                return None, "", False, f"Error: Security AST gate blocked write to '{filepath}': {scan.reason}"
        except Exception:
            pass

    is_overwrite = target.exists()
    old_text = ""
    if is_overwrite:
        try:
            raw = target.read_bytes()
            if b"\x00" in raw[:4096]:
                return None, "", True, f"Error: '{filepath}' is a binary file and cannot be overwritten as UTF-8 text."
            old_text = raw.decode("utf-8", errors="replace")
        except Exception as exc:
            return None, "", True, f"Error reading existing target '{filepath}' for diff: {exc}"

    diff_text = compute_unified_diff(str(target), old_text, content)
    return target, diff_text, is_overwrite, None


def write_outside_workspace(filepath: str, content: str) -> str:
    """
    Writes or overwrites a non-Zone-0 file outside the workspace strictly behind
    diff preview + blocking human approval. Never auto-approves unattended runs.
    """
    target, diff_text, is_overwrite, block_err = precheck_external_write(filepath, content)
    if block_err or target is None:
        return block_err or f"Error: External write to '{filepath}' was blocked."

    from autonomy.guards import is_tool_preapproved, require_side_effect_approval

    if not is_tool_preapproved("write_external_file"):
        ok, msg = require_side_effect_approval(
            "write_external_file",
            {
                "filepath": str(target),
                "content": content,
                "diff": diff_text,
                "is_overwrite": is_overwrite,
            },
        )
        if not ok:
            return f"Error: {msg}"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except Exception as exc:
        return f"Error writing external file '{filepath}': {exc}"

    out = f"Successfully wrote {len(content)} characters to external file '{target}'."
    if diff_text:
        out += f"\n[DIFF PREVIEW]:\n{diff_text}"
    return out
