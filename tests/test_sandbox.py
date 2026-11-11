"""
tests/test_sandbox.py
Phase C Workspace Sandbox tests:
- Traversal / NTFS anomaly / symlink & junction escape blocking across workspace tools
- Diff-before-overwrite computation & SSE listener timing under ZAINE_AGENT=1 vs ZAINE_AGENT=0
- Read-only outside-workspace inspection vs approval-gated external writes
- Hard-locked Zone 0 / sensitive / secret / live-vault protection
- pip install & external script fallback approval gates under ZAINE_AGENT=1
- Dynamic ZAINE_WORKSPACE resolution across helper tools
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import approval as approval_mod
import toolmaker as toolmaker_mod
import tools as tools_mod
from autonomy.loop import AutonomousLoop, LoopConfig
from autonomy.sandbox import resolve_sandbox_path


def _fake_stream(responses: List[str]):
    class FakeResp:
        def __init__(self, text: str):
            self._lines = [
                json.dumps({"message": {"content": text}}).encode("utf-8"),
                json.dumps({"done": True, "prompt_eval_count": 12, "eval_count": 8}).encode("utf-8"),
            ]
            self.raw = None

        def raise_for_status(self):
            return None

        def iter_lines(self):
            for line in self._lines:
                yield line

        def close(self):
            return None

    idx = {"i": 0}

    def _post(*args, **kwargs):
        i = idx["i"]
        idx["i"] += 1
        text = responses[i] if i < len(responses) else "Done."
        return FakeResp(text)

    return _post


def _make_junction(link_path: Path, target_dir: Path) -> bool:
    """Creates an unprivileged Windows NTFS directory junction (or POSIX symlink) for escape tests."""
    if os.name == "nt":
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link_path), str(target_dir)],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return True
    try:
        os.symlink(target_dir, link_path, target_is_directory=True)
        return True
    except OSError:
        return False


# ── 1. Traversal & NTFS Attack Vectors ───────────────────────────────────────


def test_path_traversal_and_ntfs_anomalies_blocked(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("TOP_SECRET", encoding="utf-8")
    monkeypatch.setenv("ZAINE_WORKSPACE", str(ws))
    monkeypatch.setenv("ZAINE_AGENT", "1")

    evil_paths = [
        "../outside_secret.txt",
        "sub/../../outside_secret.txt",
        "..\\outside_secret.txt",
        str(outside),
        "notes.txt:hidden_stream",
        "foo::$DATA",
        "PROGRA~1/evil.py",
        r"\\?\C:\Windows\System32\drivers\etc\hosts",
        r"\\localhost\c$\secret.txt",
        "badfile.py.",
        "badfile.py ",
    ]

    for bad in evil_paths:
        with pytest.raises(ValueError):
            resolve_sandbox_path(bad, ws)
        r_res = tools_mod.read_workspace_file(bad)
        assert r_res.startswith("Error reading file"), f"read allowed bad path {bad!r}: {r_res}"
        w_res = tools_mod.write_workspace_file(bad, "pwned")
        assert w_res.startswith("Error writing to file"), f"write allowed bad path {bad!r}: {w_res}"
        e_res = tools_mod.edit_workspace_file(bad, "TOP", "PWN")
        assert e_res.startswith("Error"), f"edit allowed bad path {bad!r}: {e_res}"
        d_res = tools_mod.delete_workspace_files(bad)
        assert d_res.startswith("Error"), f"delete allowed bad path {bad!r}: {d_res}"

    # Verify benign relative, dotfile, and legacy "workspace/" prefix still resolve cleanly inside ws
    ok_write = tools_mod.write_workspace_file("workspace/.gitignore", "*.pyc\n")
    assert ok_write.startswith("Successfully wrote")
    assert (ws / ".gitignore").read_text(encoding="utf-8") == "*.pyc\n"
    ok_dot_slash = tools_mod.write_workspace_file("./sub/ok.txt", "hello")
    assert ok_dot_slash.startswith("Successfully wrote")
    assert tools_mod.read_workspace_file("sub/ok.txt") == "hello"
    # Outside secret file remained untouched
    assert outside.read_text(encoding="utf-8") == "TOP_SECRET"


def test_junction_or_symlink_escape_blocked(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    outside_target = outside_dir / "escape.txt"
    outside_target.write_text("ORIG", encoding="utf-8")

    link_inside_ws = ws / "escape_link"
    created = _make_junction(link_inside_ws, outside_dir)
    if not created:
        pytest.skip("Neither NTFS junction nor symlink creation supported in this environment")

    monkeypatch.setenv("ZAINE_WORKSPACE", str(ws))
    try:
        with pytest.raises(ValueError, match="symlink|junction|escape|leave"):
            resolve_sandbox_path("escape_link/escape.txt", ws)

        res_write = tools_mod.write_workspace_file("escape_link/new_evil.txt", "OVERWRITE")
        assert res_write.startswith("Error writing to file")
        assert not (outside_dir / "new_evil.txt").exists()
        assert outside_target.read_text(encoding="utf-8") == "ORIG"
    finally:
        # Remove junction/symlink cleanly without leaving stray reparse point
        try:
            if os.name == "nt" and link_inside_ws.exists():
                link_inside_ws.rmdir()
            elif link_inside_ws.is_symlink():
                link_inside_ws.unlink()
        except Exception:
            pass


# ── 2. Diff-Before-Overwrite Semantics & Gate Parity ─────────────────────────


def test_diff_preview_emitted_before_overwrite_under_agent_flag(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("ZAINE_WORKSPACE", str(ws))
    monkeypatch.setenv("ZAINE_AGENT", "1")

    captured: List[Dict[str, Any]] = []

    def _listener(stage: str, tool_name: str, data: Dict[str, Any]) -> bool:
        on_disk_now = (ws / "app.py").read_text(encoding="utf-8") if (ws / "app.py").exists() else None
        captured.append(
            {
                "stage": stage,
                "tool": tool_name,
                "data": data,
                "disk_content_at_emit": on_disk_now,
            }
        )
        return True

    approval_mod.set_approval_listener(_listener)
    try:
        # Brand new file -> no overwrite diff noise
        first = tools_mod.write_workspace_file("app.py", "def greet():\n    return 'v1'\n")
        assert "[DIFF PREVIEW]" not in first
        assert captured == []

        # Overwrite via write_workspace_file -> MUST emit diff BEFORE touching disk
        second = tools_mod.write_workspace_file("app.py", "def greet():\n    return 'v2'\n")
        assert "[DIFF PREVIEW]:" in second
        assert "-    return 'v1'" in second
        assert "+    return 'v2'" in second
        assert len(captured) == 1
        assert captured[0]["stage"] == "diff_preview"
        assert captured[0]["tool"] == "write_workspace_file"
        assert captured[0]["disk_content_at_emit"] == "def greet():\n    return 'v1'\n"
        assert "-    return 'v1'" in captured[0]["data"]["diff"]
        assert (ws / "app.py").read_text(encoding="utf-8") == "def greet():\n    return 'v2'\n"

        # Targeted edit via edit_workspace_file -> ALSO emits diff BEFORE touching disk
        third = tools_mod.edit_workspace_file("app.py", "return 'v2'", "return 'v3'")
        assert "[DIFF PREVIEW]:" in third
        assert "-    return 'v2'" in third
        assert "+    return 'v3'" in third
        assert len(captured) == 2
        assert captured[1]["stage"] == "diff_preview"
        assert captured[1]["tool"] == "edit_workspace_file"
        assert captured[1]["disk_content_at_emit"] == "def greet():\n    return 'v2'\n"
    finally:
        approval_mod.clear_approval_listener()


def test_legacy_write_and_edit_unchanged_when_agent_flag_off(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("ZAINE_WORKSPACE", str(ws))
    monkeypatch.setenv("ZAINE_AGENT", "0")

    events: List[Any] = []
    approval_mod.set_approval_listener(lambda s, t, d: events.append((s, t, d)) or True)
    try:
        tools_mod.write_workspace_file("legacy.py", "x = 1\n")
        res = tools_mod.write_workspace_file("legacy.py", "x = 2\n")
        assert res == "Successfully wrote 6 characters to 'legacy.py'."
        res_edit = tools_mod.edit_workspace_file("legacy.py", "x = 2", "x = 3")
        assert res_edit == "Successfully updated 'legacy.py' with edited code."
        assert events == []
    finally:
        approval_mod.clear_approval_listener()


def test_autonomous_loop_streams_diff_preview_before_done(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "counter.py").write_text("COUNT = 1\n", encoding="utf-8")
    monkeypatch.setenv("ZAINE_WORKSPACE", str(ws))
    monkeypatch.setenv("ZAINE_AGENT", "1")
    approval_mod.clear_approval_listener()

    stream_fn = _fake_stream(
        [
            "1. Overwrite counter.py with COUNT = 2",
            json.dumps(
                {
                    "tool": "write_workspace_file",
                    "args": {"filepath": "counter.py", "content": "COUNT = 2\n"},
                }
            ),
            "Updated counter.py cleanly.",
        ]
    )
    monkeypatch.setattr("autonomy.loop.requests.post", stream_fn)

    events: List[tuple] = []
    loop = AutonomousLoop(
        config=LoopConfig(max_steps=3),
        on_event=lambda s, t, d: events.append((s, t, d)),
    )
    res = loop.run("Update COUNT in counter.py to 2")
    assert res.status == "completed"
    stages = [e[0] for e in events]
    assert "diff_preview" in stages
    assert stages.index("diff_preview") < stages.index("done")
    diff_evt = [e[2] for e in events if e[0] == "diff_preview"][0]
    assert "-COUNT = 1" in diff_evt["diff"]
    assert "+COUNT = 2" in diff_evt["diff"]


# ── 3. Outside Workspace: Read-Only vs Approval-Gated Write & Zone 0 Lock ────


def test_outside_workspace_is_readonly_unless_approved(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    ext_dir = tmp_path / "external"
    ext_dir.mkdir()
    ext_file = ext_dir / "readme.txt"
    ext_file.write_text("line1\nline2\n", encoding="utf-8")

    monkeypatch.setenv("ZAINE_WORKSPACE", str(ws))
    monkeypatch.setenv("ZAINE_AGENT", "1")

    # 1) Non-sensitive external read succeeds read-only
    read_out = tools_mod.read_external_file(str(ext_file))
    assert "[READ-ONLY OUTSIDE WORKSPACE" in read_out
    assert "line1" in read_out

    # 2) Sensitive files (live vault, .env, token json, .. traversal) cannot be read
    assert "Access denied" in tools_mod.read_external_file(str(PROJECT_ROOT / ".env"))
    assert "Access denied" in tools_mod.read_external_file(r"D:\Z.A.I.N.E vault\Z.A.I.N.E\secret.md")
    assert "Access denied" in tools_mod.read_external_file("../outside.txt")
    fake_tok = ext_dir / "gmail_token.json"
    fake_tok.write_text('{"token":"abc"}', encoding="utf-8")
    assert "Access denied" in tools_mod.read_external_file(str(fake_tok))

    # 3) Unattended external write MUST NOT auto-approve when approval denies/times out
    seen_approvals: List[Dict[str, Any]] = []
    seen_diffs: List[Dict[str, Any]] = []
    approval_mod.set_approval_listener(lambda s, t, d: seen_diffs.append({"stage": s, "tool": t, "data": d}) or True)

    def _deny_approval(**kwargs):
        seen_approvals.append(kwargs)
        return False, "Timed out awaiting operator approval"

    monkeypatch.setattr(approval_mod, "require_approval", _deny_approval)
    try:
        denied = tools_mod.write_external_file(str(ext_file), "line1\nline2_changed\n")
        assert "Approval required / denied" in denied
        assert ext_file.read_text(encoding="utf-8") == "line1\nline2\n"
        # Diff preview MUST have been emitted & sent in approval payload even when denied
        assert any(d["stage"] == "diff_preview" for d in seen_diffs)
        assert len(seen_approvals) == 1
        assert "-line2" in seen_approvals[0]["code_or_cmd"]
        assert "+line2_changed" in seen_approvals[0]["code_or_cmd"]

        # 4) Zone 0 kernel files and secrets are HARD BLOCKED BEFORE approval is ever prompted
        seen_approvals.clear()
        z0 = tools_mod.write_external_file(str(PROJECT_ROOT / "approval.py"), "# hacked")
        assert "Zone 0 kernel file" in z0
        z_env = tools_mod.write_external_file(str(PROJECT_ROOT / ".env"), "KEY=evil")
        assert "Access denied" in z_env
        z_vault = tools_mod.write_external_file(r"D:\Z.A.I.N.E vault\Z.A.I.N.E\injected.md", "# evil")
        assert "Access denied" in z_vault
        assert seen_approvals == []

        # 5) Explicitly approved external write succeeds and returns diff
        monkeypatch.setattr(approval_mod, "require_approval", lambda **kw: seen_approvals.append(kw) or (True, "Approved"))
        approved = tools_mod.write_external_file(str(ext_file), "line1\nline2_changed\n")
        assert approved.startswith("Successfully wrote")
        assert "[DIFF PREVIEW]:" in approved
        assert ext_file.read_text(encoding="utf-8") == "line1\nline2_changed\n"
        assert len(seen_approvals) == 1
    finally:
        approval_mod.clear_approval_listener()


def test_autonomous_loop_external_write_blocks_zone0_and_approves_safe_target(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    ext = tmp_path / "outside_notes.md"
    ext.write_text("# Old\n", encoding="utf-8")

    monkeypatch.setenv("ZAINE_WORKSPACE", str(ws))
    monkeypatch.setenv("ZAINE_AGENT", "1")
    approval_mod.clear_approval_listener()

    approval_calls: List[Dict[str, Any]] = []
    monkeypatch.setattr(
        approval_mod,
        "require_approval",
        lambda **kw: approval_calls.append(kw) or (True, "Approved by operator"),
    )

    stream_fn = _fake_stream(
        [
            "1. Try writing outside notes with approval",
            json.dumps(
                {
                    "tool": "write_external_file",
                    "args": {"filepath": str(ext), "content": "# Old\n# New Line\n"},
                }
            ),
            "Done.",
        ]
    )
    monkeypatch.setattr("autonomy.loop.requests.post", stream_fn)

    events: List[tuple] = []
    loop = AutonomousLoop(config=LoopConfig(max_steps=3), on_event=lambda s, t, d: events.append((s, t, d)))
    res = loop.run(f"Append '# New Line' to {ext}")
    assert res.status == "completed"
    assert ext.read_text(encoding="utf-8") == "# Old\n# New Line\n"
    assert str(ext) in res.artifacts
    assert len(approval_calls) == 1
    assert "+# New Line" in approval_calls[0]["code_or_cmd"]
    assert any(e[0] == "diff_preview" for e in events)


# ── 4. pip install & External Script Fallback Guards + Dynamic Workspace ─────


def test_pip_install_and_external_script_require_approval_under_agent_flag(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("ZAINE_WORKSPACE", str(ws))
    monkeypatch.setenv("ZAINE_AGENT", "1")

    pip_ran = {"called": False}
    monkeypatch.setattr(toolmaker_mod.subprocess, "run", lambda *a, **kw: pip_ran.update({"called": True}))
    monkeypatch.setattr(approval_mod, "require_approval", lambda **kw: (False, "Denied by policy"))

    out = toolmaker_mod.install_python_package("somepkg")
    assert "Approval required / denied" in out
    assert pip_ran["called"] is False

    # Running a project-root script outside workspace also requires approval under ZAINE_AGENT=1
    out_script = tools_mod.run_python_script("agent.py")
    assert "Approval required / denied" in out_script

    # Path traversal in run_python_script is rejected outright before fallback
    evil_script = tools_mod.run_python_script("../agent.py")
    assert "Access denied" in evil_script


def test_deep_search_uses_dynamic_workspace_dir(tmp_path, monkeypatch):
    ws1 = tmp_path / "ws_one"
    ws2 = tmp_path / "ws_two"
    ws1.mkdir()
    ws2.mkdir()
    (ws1 / "alpha_only.py").write_text("# alpha_marker_unique\n", encoding="utf-8")
    (ws2 / "beta_only.py").write_text("# beta_marker_unique\n", encoding="utf-8")

    # Even if WORKSPACE_DIR at import pointed elsewhere, switching ZAINE_WORKSPACE updates deep_search
    monkeypatch.setenv("ZAINE_WORKSPACE", str(ws2))
    res = tools_mod.deep_search("beta_marker_unique")
    assert "beta_only.py" in res
    assert "alpha_only.py" not in res

