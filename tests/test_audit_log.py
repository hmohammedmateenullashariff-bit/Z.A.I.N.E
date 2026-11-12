"""
tests/test_audit_log.py
Phase G tests — Per-run JSON Audit Trail:
- Records (agent, tool, redacted/bounded args summary, result, approval decisions, timestamps)
- Captures real ApprovalRegistry APPROVE / DENY decisions and agent permission blocks
- Correlates parent + delegated subagent calls chronologically inside one parent audit file
- Persists cleanly on circuit-breaker / early stop and appends seamlessly across resume()
- Exposes authenticated GET /api/audit & /api/audit/<run_id>, agent_run.audit_path, and /runs audit in TUI
- Leaves ZAINE_AGENT=0 behavior completely free of stray audit writes
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agents
import approval as approval_mod
import core_service
from autonomy import (
    AuditLogStore,
    AutonomousLoop,
    LoopConfig,
    RunScratchpadStore,
)
from core.circuit_breaker import CircuitBreakerManager
from tui.widgets.chat import AssistantTurnCard


def _stream_factory(responses: List[str]):
    """Builds a deterministic streaming Ollama mock yielding sequential scripted responses."""
    idx = {"i": 0}

    def _stream(payload: Dict[str, Any], cancel_token: Any, timeout_s: float) -> Iterator[Dict[str, Any]]:
        i = idx["i"]
        idx["i"] += 1
        text = responses[i] if i < len(responses) else "Finished."
        yield {"message": {"content": text}, "done": False}
        yield {
            "message": {"content": ""},
            "done": True,
            "prompt_eval_count": 32,
            "eval_count": 14,
        }

    return _stream


@pytest.fixture()
def audit_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ws = tmp_path / "workspace"
    runs_dir = tmp_path / "runs"
    audit_dir = tmp_path / "audit"
    vault_dir = tmp_path / "dev_vault"
    for d in (ws, runs_dir, audit_dir, vault_dir):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("ZAINE_AGENT", "1")
    monkeypatch.setenv("ZAINE_WORKSPACE", str(ws))
    monkeypatch.setenv("ZAINE_RUNS_DIR", str(runs_dir))
    monkeypatch.setenv("ZAINE_AUDIT_DIR", str(audit_dir))
    monkeypatch.setenv("ZAINE_OBSIDIAN_VAULT_PATH", str(vault_dir))

    yield {
        "ws": ws,
        "runs_dir": runs_dir,
        "audit_dir": audit_dir,
        "vault_dir": vault_dir,
    }


def test_audit_records_tool_redaction_permission_block_and_timestamps(audit_env):
    """Restricted profile logs allowed read-only call (with redacted secret args), blocked call, and ISO timestamps."""
    planner = agents.get_registry().resolve("planner").for_subagent()

    def _tool_exec(tc: Dict[str, Any]) -> str:
        if tc["tool"] == "recall":
            return "Recalled memory snippet: local sqlite row 42"
        return "unexpected"

    big_payload = "A" * 500
    stream_fn = _stream_factory([
        "1. Recall notes\n2. Attempt disallowed command",
        json.dumps({"tool": "recall", "args": {"query": big_payload, "content": big_payload, "api_token": "super-secret-xyz"}}),
        json.dumps({"tool": "execute_command", "args": {"command": "echo hacked"}}),
        "Done checking memory.",
    ])

    loop = AutonomousLoop(
        config=LoopConfig(max_steps=4, model_name="zaine-reflex-7b"),
        profile=planner,
        model_stream_fn=stream_fn,
        tool_exec_fn=_tool_exec,
        breaker=CircuitBreakerManager(),
        persist_scratchpad=True,
        persist_audit=True,
    )
    res = loop.run("Inspect planner notes safely", run_id="RUN-AUDIT-01")
    assert res.status == "completed"
    assert res.audit_path
    audit_file = Path(res.audit_path)
    assert audit_file.exists()
    assert audit_file.parent == audit_env["audit_dir"]

    data = json.loads(audit_file.read_text(encoding="utf-8"))
    assert data["run_id"] == "RUN-AUDIT-01"
    assert data["root_agent_id"] == "zaine-jarvis"
    assert data["model_name"] == "zaine-reflex-7b"
    assert data["status"] == "completed"
    assert data["started_at"] and data["ended_at"]
    assert data["privacy_taint"] == "LOCAL_ONLY"
    assert len(data["entries"]) == 2

    e0, e1 = data["entries"]
    assert e0["agent"] == "zaine-jarvis"
    assert e0["tool"] == "recall"
    assert e0["result_status"] == "ok"
    assert e0["approval_decision"]["decision"] == "NOT_REQUIRED"
    assert "api_token=<redacted>" in e0["args_summary"]
    assert "super-secret-xyz" not in e0["args_summary"]
    assert "500 chars" in e0["args_summary"]
    assert len(e0["args_summary"]) <= 260
    assert e0["timestamp"]
    assert "local sqlite row 42" in e0["result_summary"]

    assert e1["tool"] == "execute_command"
    assert e1["result_status"] == "denied"
    assert e1["approval_decision"]["decision"] == "BLOCKED_PERMISSION"
    assert any(
        ap["tool"] == "execute_command" and ap["decision"] == "BLOCKED_PERMISSION"
        for ap in data["approval_decisions"]
    )


def test_audit_captures_real_approval_registry_approve_and_deny(audit_env):
    """Real ApprovalRegistry APPROVE & DENY flows are audited with matching proposal_id without duplicates."""
    orch = agents.get_registry().resolve("jarvis")
    executed_cmds: List[str] = []

    def _tool_exec(tc: Dict[str, Any]) -> str:
        cmd = str((tc.get("args") or {}).get("command") or "")
        executed_cmds.append(cmd)
        return f"ran:{cmd}"

    # Drive real ApprovalRegistry in-process: approve 1st proposal, deny 2nd proposal
    approval_counter = {"n": 0}

    def _listener(stage: str, tool_name: str, data: Any) -> bool:
        if stage == "approval_required" and isinstance(data, dict):
            pid = str(data.get("proposal_id") or "")
            if pid:
                approval_counter["n"] += 1
                if approval_counter["n"] == 1:
                    threading.Thread(
                        target=lambda: approval_mod.ApprovalRegistry.approve(pid, note="Operator approved step 1"),
                        daemon=True,
                    ).start()
                else:
                    threading.Thread(
                        target=lambda: approval_mod.ApprovalRegistry.deny(pid, note="Operator denied step 2"),
                        daemon=True,
                    ).start()
        return True

    approval_mod.set_approval_listener(_listener)
    try:
        stream_fn = _stream_factory([
            "1. Run first shell check\n2. Attempt second shell command",
            json.dumps({"tool": "execute_command", "args": {"command": "echo first"}}),
            json.dumps({"tool": "execute_command", "args": {"command": "echo second"}}),
            "Completed with one approved and one denied shell call.",
        ])

        loop = AutonomousLoop(
            config=LoopConfig(max_steps=4),
            profile=orch,
            model_stream_fn=stream_fn,
            tool_exec_fn=_tool_exec,
            breaker=CircuitBreakerManager(),
        )
        res = loop.run("Run shell commands with approval", run_id="RUN-AUDIT-APPR")
    finally:
        approval_mod.clear_approval_listener()

    assert res.status == "completed"
    assert executed_cmds == ["echo first"]

    loaded = AuditLogStore(audit_env["audit_dir"]).load("RUN-AUDIT-APPR")
    assert loaded is not None
    assert len(loaded.entries) == 2
    assert loaded.entries[0]["approval_decision"]["decision"] == "APPROVED"
    assert loaded.entries[0]["result_status"] == "ok"
    assert loaded.entries[1]["approval_decision"]["decision"] == "DENIED"
    assert loaded.entries[1]["result_status"] == "denied"

    # Exactly 2 approval decisions recorded (no spurious duplicate PREAPPROVED for same tool)
    assert len(loaded.approval_decisions) == 2
    d0, d1 = loaded.approval_decisions
    assert d0["decision"] == "APPROVED" and d0["proposal_id"].startswith("ACT-") and "step 1" in d0["note"]
    assert d1["decision"] == "DENIED" and d1["proposal_id"].startswith("ACT-") and "step 2" in d1["note"]
    assert d0["proposal_id"] != d1["proposal_id"]


def test_audit_correlates_parent_and_delegated_subagent_in_one_file(audit_env):
    """Parent and child subagent tool calls land chronologically in ONE <parent_run_id>.json file."""
    orch = agents.get_registry().resolve("jarvis")
    ws = audit_env["ws"]

    def _tool_exec(tc: Dict[str, Any]) -> str:
        tool = tc["tool"]
        args = tc.get("args") or {}
        if tool == "write_workspace_file":
            p = ws / str(args.get("filepath", "out.py"))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(args.get("content", "")), encoding="utf-8")
            return f"Wrote {p.name}"
        return f"Unexpected tool {tool}"

    # Parent streams steps 1..2 and final reply; subagent (`coder`) streams steps 1..4 in between
    turns = iter([
        "1. Delegate file creation to coder",
        json.dumps({"tool": "delegate", "args": {"agent_id": "coder", "task": "Create helper.py"}}),
        "1. Write helper.py\n2. Attempt disallowed shell",
        json.dumps({"tool": "write_workspace_file", "args": {"filepath": "helper.py", "content": "def f(): return 7\n"}}),
        json.dumps({"tool": "execute_command", "args": {"command": "whoami"}}),
        "Created helper.py; execute_command was blocked as expected.",
        "Delegation complete and verified.",
    ])

    def _shared_stream(payload: Dict[str, Any], cancel_token: Any, timeout_s: float) -> Iterator[Dict[str, Any]]:
        txt = next(turns)
        yield {"message": {"content": txt}, "done": False}
        yield {"message": {"content": ""}, "done": True, "prompt_eval_count": 20, "eval_count": 10}

    loop = AutonomousLoop(
        config=LoopConfig(max_steps=4),
        profile=orch,
        model_stream_fn=_shared_stream,
        tool_exec_fn=_tool_exec,
        breaker=CircuitBreakerManager(),
    )
    res = loop.run("Create helper.py via coder", run_id="RUN-AUDIT-DELEG")
    assert res.status == "completed"

    # Only ONE audit file exists for the whole parent+child execution
    audit_files = list(audit_env["audit_dir"].glob("*.json"))
    assert len(audit_files) == 1
    assert audit_files[0].name == "RUN-AUDIT-DELEG.json"

    audit = AuditLogStore(audit_env["audit_dir"]).load("RUN-AUDIT-DELEG")
    assert audit is not None
    # Child entries record BEFORE parent delegate call returns, followed by delegate summary entry
    tools_seq = [
        (e["agent"], e["delegation_depth"], e["tool"], (e["approval_decision"] or {}).get("decision"))
        for e in audit.entries
    ]
    assert tools_seq == [
        ("zaine-edith", 1, "write_workspace_file", "NOT_REQUIRED"),
        ("zaine-edith", 1, "execute_command", "BLOCKED_PERMISSION"),
        ("zaine-jarvis", 0, "delegate", "NOT_REQUIRED"),
    ]
    assert any("helper.py" in a for a in audit.artifacts)
    assert any(a["agent"] == "zaine-edith" and a["decision"] == "BLOCKED_PERMISSION" for a in audit.approval_decisions)


def test_audit_breaker_stop_and_append_across_resume(audit_env):
    """Circuit breaker stop writes finalized audit; stopped_max_steps + resume() appends cleanly."""
    orch = agents.get_registry().resolve("jarvis")

    def _failing_tool(tc: Dict[str, Any]) -> str:
        return "Error: simulated failure"

    # Part A: Circuit breaker stop (3 identical failures)
    breaker_stream = _stream_factory([
        "1. Try broken tool",
        json.dumps({"tool": "recall", "args": {"query": "broken"}}),
        json.dumps({"tool": "recall", "args": {"query": "broken"}}),
        json.dumps({"tool": "recall", "args": {"query": "broken"}}),
    ])
    cb_loop = AutonomousLoop(
        config=LoopConfig(max_steps=5, identical_failure_limit=3),
        profile=orch,
        model_stream_fn=breaker_stream,
        tool_exec_fn=_failing_tool,
        breaker=CircuitBreakerManager(),
    )
    cb_res = cb_loop.run("Trigger breaker", run_id="RUN-AUDIT-CB")
    assert cb_res.status == "stopped_circuit_breaker"
    cb_audit = AuditLogStore(audit_env["audit_dir"]).load("RUN-AUDIT-CB")
    assert cb_audit is not None
    assert cb_audit.status == "stopped_circuit_breaker"
    assert "Circuit breaker tripped" in cb_audit.stop_reason
    assert len(cb_audit.entries) == 3

    # Part B: Stop at max_steps=1 then resume for step 2 using same run_id
    def _ok_tool(tc: Dict[str, Any]) -> str:
        return f"ok:{(tc.get('args') or {}).get('query', '')}"

    part1_stream = _stream_factory([
        "1. Step one\n2. Step two",
        json.dumps({"tool": "recall", "args": {"query": "step1"}}),
    ])
    pad_store = RunScratchpadStore(audit_env["runs_dir"])
    aud_store = AuditLogStore(audit_env["audit_dir"])
    loop1 = AutonomousLoop(
        config=LoopConfig(max_steps=1),
        profile=orch,
        model_stream_fn=part1_stream,
        tool_exec_fn=_ok_tool,
        breaker=CircuitBreakerManager(),
        scratchpad_store=pad_store,
        audit_store=aud_store,
    )
    res1 = loop1.run("Two-part resumable task", run_id="RUN-AUDIT-RESUME")
    assert res1.status == "stopped_max_steps"
    after_p1 = aud_store.load("RUN-AUDIT-RESUME")
    assert after_p1 is not None and len(after_p1.entries) == 1
    assert after_p1.status == "stopped_max_steps"

    part2_stream = _stream_factory([
        json.dumps({"tool": "recall", "args": {"query": "step2"}}),
        "Both parts finished.",
    ])
    loop2 = AutonomousLoop(
        config=LoopConfig(max_steps=2),
        profile=orch,
        model_stream_fn=part2_stream,
        tool_exec_fn=_ok_tool,
        breaker=CircuitBreakerManager(),
        scratchpad_store=pad_store,
        audit_store=aud_store,
    )
    res2 = loop2.resume("RUN-AUDIT-RESUME", additional_steps=2, scratchpad_store=pad_store, audit_store=aud_store)
    assert res2.status == "completed"
    after_p2 = aud_store.load("RUN-AUDIT-RESUME")
    assert after_p2 is not None
    assert after_p2.status == "completed"
    assert len(after_p2.entries) == 2
    assert "step1" in after_p2.entries[0]["args_summary"]
    assert "step2" in after_p2.entries[1]["args_summary"]


def test_core_service_audit_endpoints_and_stream_payload(audit_env, monkeypatch):
    """CoreService GET /api/audit, GET /api/audit/<id>, /api/runs audit_path, and done.agent_run."""
    from autonomy.loop import LoopResult

    orch = agents.get_registry().resolve("jarvis")
    loop = AutonomousLoop(
        config=LoopConfig(max_steps=3),
        profile=orch,
        model_stream_fn=_stream_factory([
            "1. Recall item",
            json.dumps({"tool": "recall", "args": {"query": "hello"}}),
            "Done.",
        ]),
        tool_exec_fn=lambda tc: "ok-recall",
        breaker=CircuitBreakerManager(),
    )
    res = loop.run("Check audit endpoint", run_id="RUN-HTTP-AUD")
    assert res.audit_path

    class _StubAgent:
        last_tool_called = None
        ultron_mode = False
        last_agent_selection = None
        last_turn_calls = []
        last_loop_result = None

        def chat_stream(
            self,
            user_msg,
            on_tool_event=None,
            cancel_check=None,
            request_id=None,
            force_autonomous=False,
            resume_run_id=None,
        ):
            self.last_loop_result = LoopResult(
                run_id="RUN-HTTP-AUD",
                status="completed",
                summary="Done.",
                plan=["Step 1"],
                steps_executed=1,
                max_steps=3,
                stop_reason="completed",
                elapsed_s=0.01,
                audit_path=res.audit_path,
            )
            yield "Done."

    class _StubCore:
        auth_token = "phase-g-token"
        warming = False
        current_mode = "jarvis"
        current_status = "idle"
        port = 0
        model_loaded = True

        def __init__(self):
            self.agent = _StubAgent()

        def set_status(self, _s):
            return None

    srv = ThreadingHTTPServer(("127.0.0.1", 0), core_service.CoreServiceRequestHandler)
    srv.core_service_instance = _StubCore()
    port = srv.server_address[1]
    srv.core_service_instance.port = port
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    base = f"http://127.0.0.1:{port}"
    headers = {"X-Zaine-Token": "phase-g-token", "Content-Type": "application/json"}

    try:
        # Unauthenticated requests rejected
        assert requests.get(f"{base}/api/audit", timeout=3).status_code == 401
        assert requests.get(f"{base}/api/audit/RUN-HTTP-AUD", timeout=3).status_code == 401

        # /api/runs attaches audit_path
        runs_resp = requests.get(f"{base}/api/runs", headers=headers, timeout=3)
        assert runs_resp.status_code == 200
        runs_list = runs_resp.json()["runs"]
        assert any(r["run_id"] == "RUN-HTTP-AUD" and r["audit_path"] == res.audit_path for r in runs_list)

        # /api/audit lists summary
        list_resp = requests.get(f"{base}/api/audit", headers=headers, timeout=3)
        assert list_resp.status_code == 200
        audits = list_resp.json()["audits"]
        assert len(audits) == 1
        assert audits[0]["run_id"] == "RUN-HTTP-AUD"
        assert audits[0]["entry_count"] == 1

        # /api/audit/<run_id> returns full trail
        one_resp = requests.get(f"{base}/api/audit/RUN-HTTP-AUD", headers=headers, timeout=3)
        assert one_resp.status_code == 200
        body = one_resp.json()
        assert body["ok"] is True
        assert body["audit_path"] == res.audit_path
        assert body["audit"]["entries"][0]["tool"] == "recall"

        # Invalid & missing IDs handled safely
        assert requests.get(f"{base}/api/audit/..%2Fsecret", headers=headers, timeout=3).status_code == 400
        assert requests.get(f"{base}/api/audit/RUN-NO-SUCH", headers=headers, timeout=3).status_code == 404

        # /api/chat/stream done.agent_run includes audit_path
        stream_resp = requests.post(
            f"{base}/api/chat/stream",
            headers=headers,
            json={"message": "Check", "force_autonomous": True},
            timeout=5,
        )
        assert stream_resp.status_code == 200
        assert "audit_path" in stream_resp.text
        assert "RUN-HTTP-AUD" in stream_resp.text
    finally:
        srv.shutdown()
        srv.server_close()


class TestTUIRunsAuditCommand(unittest.IsolatedAsyncioTestCase):

    async def test_tui_runs_audit_renders_summary_and_detail(self):
        import os
        import tui.app as tui_app_mod
        from tui.app import ZaineTUI

        sample_list = {
            "ok": True,
            "audits": [
                {
                    "run_id": "RUN-TUI-AUD1",
                    "root_agent_id": "zaine-jarvis",
                    "status": "completed",
                    "entry_count": 2,
                    "approval_count": 1,
                    "started_at": "2026-11-12T06:00:00Z",
                    "ended_at": "2026-11-12T06:00:03Z",
                }
            ],
        }
        sample_detail = {
            "ok": True,
            "audit_path": "/tmp/audit/RUN-TUI-AUD1.json",
            "audit": {
                "run_id": "RUN-TUI-AUD1",
                "status": "completed",
                "stop_reason": "completed",
                "root_agent_id": "zaine-jarvis",
                "steps_executed": 2,
                "max_steps": 4,
                "privacy_taint": "LOCAL_ONLY",
                "approval_decisions": [{"tool": "execute_command", "decision": "APPROVED"}],
                "entries": [
                    {
                        "agent": "zaine-jarvis",
                        "tool": "execute_command",
                        "result_status": "ok",
                        "approval_decision": {"decision": "APPROVED", "proposal_id": "APR-TUI-1"},
                        "args_summary": "command='pytest'",
                    }
                ],
            },
        }

        async def _fake_get_audit(run_id: str = "", base_url: str | None = None):
            return sample_detail if run_id else sample_list

        orig_get_audit = tui_app_mod.get_audit
        orig_flag = os.environ.get("ZAINE_AGENT")
        tui_app_mod.get_audit = _fake_get_audit
        os.environ["ZAINE_AGENT"] = "1"
        try:
            app = ZaineTUI()
            async with app.run_test(size=(150, 42)) as pilot:
                app._dispatch_user_turn("/runs audit")
                await pilot.pause(0.15)
                msgs = [m.markdown_text for m in app.query(AssistantTurnCard)]
                self.assertTrue(any("RUN-TUI-AUD1" in m and "Autonomous Run Audit Logs" in m for m in msgs))

                app._dispatch_user_turn("/runs audit RUN-TUI-AUD1")
                await pilot.pause(0.15)
                msgs2 = [m.markdown_text for m in app.query(AssistantTurnCard)]
                self.assertTrue(any("Run Audit: `RUN-TUI-AUD1`" in m and "APPROVED" in m for m in msgs2))
        finally:
            tui_app_mod.get_audit = orig_get_audit
            if orig_flag is None:
                os.environ.pop("ZAINE_AGENT", None)
            else:
                os.environ["ZAINE_AGENT"] = orig_flag


def test_zaine_agent_zero_creates_no_audit_files(audit_env, monkeypatch):
    """When ZAINE_AGENT=0, audit directory stays untouched on normal status/router queries."""
    monkeypatch.setenv("ZAINE_AGENT", "0")
    from autonomy.audit import get_audit_dir
    assert get_audit_dir() == audit_env["audit_dir"]
    assert list(audit_env["audit_dir"].glob("*.json")) == []
