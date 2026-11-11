"""
tests/test_tui_phase_f.py
Phase F verification tests:
- AgentStateHUD displays real agent, step n/max, tool in use, queue, and defaults to "n/a" (no fake values)
- Narrow HUD truncation preserves ellipsis without wrapping
- ExecGraph tracks AutonomousLoop lifecycle events
- CoreService /api/runs (X-Zaine-Token authenticated), /api/status queue, /api/run, /api/runs/resume, and /api/chat/cancel (/stop)
- Simulated crash mid-run appears as interrupted (resumable) on /runs and resumes cleanly
- ZaineTUI slash commands: /run, /runs, /stop work cleanly while /agent and /agents remain untouched
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from textual.geometry import Size

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autonomy.scratchpad import RunScratchpad, RunScratchpadStore
from tui.exec_graph import ExecGraph
from tui.widgets.chat import AssistantTurnCard, ChatLog, SystemCard
from tui.widgets.hud import AgentStateHUD


def test_hud_defaults_to_na_and_updates_real_execution_fields():
    """HUD must never show fake values: starts at 'n/a' and displays real step/tool/queue updates."""
    hud = AgentStateHUD()
    hud._size = Size(44, 38)
    initial_text = hud.render().plain

    assert "Agent" in initial_text
    assert "Run" in initial_text
    assert "Step" in initial_text
    assert "Tool" in initial_text
    assert "Queue" in initial_text
    assert "n/a" in initial_text

    hud.update_agent("E.D.I.T.H.", title="Coder", reason="coding task", pinned=False)
    hud.update_execution_state(
        run_id="RUN-F01",
        run_status="running",
        step="2/6",
        tool_in_use="read_file",
        queue="1 queued (1 active)",
    )
    live_text = hud.render().plain
    assert "E.D.I.T.H." in live_text
    assert "RUN-F01 (running)" in live_text
    assert "2/6" in live_text
    assert "read_file" in live_text
    assert "1 queued (1 active)" in live_text

    hud.update_execution_state(tool_in_use="n/a", run_status="completed")
    after_tool = hud.render().plain
    assert "RUN-F01 (completed)" in after_tool
    assert "read_file" not in after_tool


def test_hud_narrow_width_truncates_execution_rows_with_ellipsis():
    """Narrow HUD (38 cols) truncates long execution fields with ellipsis rather than wrapping."""
    hud = AgentStateHUD()
    hud._size = Size(38, 38)
    hud.update_execution_state(
        run_id="RUN-VERYLONGIDENTIFIER123456789",
        run_status="running",
        step="100/200",
        tool_in_use="extremely_long_autonomous_tool_name_for_hud_test",
        queue="12 queued (1 active)",
    )
    rendered = hud.render().plain
    tool_lines = [line for line in rendered.splitlines() if line.lstrip().startswith("Tool")]
    run_lines = [line for line in rendered.splitlines() if line.lstrip().startswith("Run")]
    assert len(tool_lines) == 1
    assert "…" in tool_lines[0]
    assert len(run_lines) == 1
    assert "…" in run_lines[0]


def test_exec_graph_records_autonomous_events():
    """ExecGraph must log plan, resume, step, observe, reflect, and circuit_breaker events."""
    g = ExecGraph()
    g.start_turn("Build calculator")
    g.apply({"type": "tool_event", "stage": "plan_start", "tool": "loop", "data": {"run_id": "R1", "max_steps": 5}})
    g.apply({"type": "tool_event", "stage": "plan", "tool": "loop", "data": {"run_id": "R1", "plan": ["Write script", "Test"]}})
    g.apply({"type": "tool_event", "stage": "step", "tool": "zaine-coder", "data": {"run_id": "R1", "step": 1, "max_steps": 5, "plan_step": "Write script"}})
    g.apply({"type": "tool_event", "stage": "observe", "tool": "write_file", "data": {"status": "ok", "preview": "wrote calc.py"}})
    g.apply({"type": "tool_event", "stage": "reflect", "tool": "loop", "data": {"step": 1, "action": "continue"}})
    g.apply({"type": "tool_event", "stage": "resume", "tool": "loop", "data": {"run_id": "R1", "start_step": 2, "max_steps": 5}})
    g.apply({"type": "tool_event", "stage": "circuit_breaker", "tool": "loop", "data": {"reason": "repeated failures"}})
    channels = [c for _, c, _ in g.events]
    assert "PLAN" in channels
    assert "STEP" in channels
    assert "OBS" in channels
    assert "REFLECT" in channels
    assert "RESUME" in channels
    assert "STOP" in channels


def test_core_service_runs_auth_resume_and_stop(tmp_path, monkeypatch):
    """Verifies /api/runs auth, simulated crash visibility, /api/run ZAINE_AGENT gating, and /api/chat/cancel."""
    import requests
    import core_service
    from autonomy.cancel import CancelToken, register_active_run, unregister_active_run
    from autonomy.loop import LoopResult

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ZAINE_RUNS_DIR", str(runs_dir))

    store = RunScratchpadStore(base_dir=runs_dir)
    crashed_pad = RunScratchpad(
        run_id="RUN-CRASH-99",
        task="Create hello.py and test it",
        agent_id="zaine-jarvis",
        status="running",
        pid=999999,
        plan=["Plan solution", "Write script", "Verify tests"],
        current_step=2,
        completed_steps=1,
        max_steps=6,
        artifacts=["hello.py"],
    )
    store.save(crashed_pad)

    recorded_calls: List[Dict[str, Any]] = []

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
            recorded_calls.append({
                "user_msg": user_msg,
                "force_autonomous": force_autonomous,
                "resume_run_id": resume_run_id,
                "request_id": request_id,
            })
            if on_tool_event:
                on_tool_event("plan_start", "loop", {"run_id": resume_run_id or "RUN-NEW-1", "max_steps": 4})
                on_tool_event("step", "zaine-jarvis", {"run_id": resume_run_id or "RUN-NEW-1", "step": 2, "max_steps": 4, "phase": "act"})
            self.last_loop_result = LoopResult(
                run_id=resume_run_id or "RUN-NEW-1",
                status="completed",
                summary="Done via stub autonomous stream.",
                plan=["Step 1"],
                steps_executed=2,
                max_steps=4,
                stop_reason="completed",
                elapsed_s=0.02,
            )
            yield "Done via stub autonomous stream."

    class _StubCore:
        auth_token = "phase-f-token"
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
    headers = {"X-Zaine-Token": "phase-f-token", "Content-Type": "application/json"}

    try:
        # 1. /api/runs requires X-Zaine-Token
        unauth = requests.get(f"{base}/api/runs", timeout=3)
        assert unauth.status_code == 401

        # 2. Under ZAINE_AGENT=0: /api/runs lists crashed scratchpad as interrupted (resumable),
        #    while /api/run and force_autonomous /api/chat/stream reject execution cleanly.
        monkeypatch.setenv("ZAINE_AGENT", "0")
        runs_resp = requests.get(f"{base}/api/runs", headers=headers, timeout=3)
        assert runs_resp.status_code == 200
        runs_data = runs_resp.json()
        assert runs_data["ok"] is True
        assert runs_data["agent_enabled"] is False
        assert len(runs_data["runs"]) == 1
        r0 = runs_data["runs"][0]
        assert r0["run_id"] == "RUN-CRASH-99"
        assert r0["crashed"] is True
        assert r0["resumable"] is True
        assert r0["effective_status"] == "interrupted (resumable)"

        blocked_run = requests.post(f"{base}/api/run", headers=headers, json={"message": "Build demo"}, timeout=3)
        assert blocked_run.status_code == 400
        assert "ZAINE_AGENT=1" in blocked_run.json()["error"]

        # 3. /api/status exposes queue telemetry
        status_resp = requests.get(f"{base}/api/status", headers=headers, timeout=3)
        assert status_resp.status_code == 200
        assert "queue" in status_resp.json()
        assert "queue_depth" in status_resp.json()["queue"]

        # 4. Under ZAINE_AGENT=1: /api/chat/stream with force_autonomous & /api/runs/resume forward properly
        monkeypatch.setenv("ZAINE_AGENT", "1")
        stream_resp = requests.post(
            f"{base}/api/chat/stream",
            headers=headers,
            json={"message": "Create calc.py", "request_id": "req-f1", "force_autonomous": True},
            timeout=5,
        )
        assert stream_resp.status_code == 200
        assert '"type": "done"' in stream_resp.text
        assert recorded_calls[-1]["force_autonomous"] is True

        resume_resp = requests.post(
            f"{base}/api/runs/resume",
            headers=headers,
            json={"run_id": "RUN-CRASH-99", "request_id": "req-f2"},
            timeout=5,
        )
        assert resume_resp.status_code == 200
        assert '"RUN-CRASH-99"' in resume_resp.text
        assert recorded_calls[-1]["resume_run_id"] == "RUN-CRASH-99"

        # Missing run returns 404
        missing_resp = requests.post(
            f"{base}/api/runs/resume",
            headers=headers,
            json={"run_id": "RUN-DOES-NOT-EXIST"},
            timeout=3,
        )
        assert missing_resp.status_code == 404

        # 5. /api/chat/cancel with empty request_id stops active autonomous run (/stop behavior)
        tok = CancelToken()
        register_active_run("RUN-LIVE-STOP", "req-live-stop", tok)
        try:
            stop_resp = requests.post(f"{base}/api/chat/cancel", headers=headers, json={}, timeout=3)
            assert stop_resp.status_code == 200
            stop_data = stop_resp.json()
            assert stop_data["ok"] is True
            assert stop_data["cancelled_runs"] >= 1
            assert tok.cancelled is True
        finally:
            unregister_active_run("RUN-LIVE-STOP")
    finally:
        srv.shutdown()
        srv.server_close()


def test_single_model_router_under_agent_flag(monkeypatch):
    """Under ZAINE_AGENT=1 and ZAINE_SINGLE_MODEL=1, router exposes only zaine-reflex-7b."""
    from core_router import router
    monkeypatch.setenv("ZAINE_AGENT", "1")
    monkeypatch.setenv("ZAINE_SINGLE_MODEL", "1")
    monkeypatch.delenv("ZAINE_AGENT_MODEL", raising=False)
    assert router.reflex_model == "zaine-reflex-7b"
    assert router.deep_model == "zaine-reflex-7b"
    assert router.coder_model == "zaine-reflex-7b"

    monkeypatch.setenv("ZAINE_AGENT", "0")
    monkeypatch.setenv("ZAINE_FAST", "1")
    assert router.reflex_model == "zaine-fast-3b"


class TestTUIPhaseFCommands(unittest.IsolatedAsyncioTestCase):

    async def test_tui_run_runs_stop_and_untouched_agent_commands(self):
        """Textual Pilot verifies /run, /runs, /stop, HUD live updates, and untouched /agent + /agents."""
        import os
        import tui.app as tui_app_mod
        from tui.app import ZaineTUI

        orig_env = os.environ.get("ZAINE_AGENT")
        try:
            # 1. Verify ZAINE_AGENT=0 blocks /run cleanly without streaming
            os.environ["ZAINE_AGENT"] = "0"
            app_off = ZaineTUI()
            async with app_off.run_test(size=(150, 42)) as pilot:
                app_off._dispatch_user_turn("/run build something")
                await pilot.pause(0.1)
                cards = app_off.query(SystemCard)
                self.assertTrue(any("AUTONOMOUS MODE DISABLED" in c.title_text for c in cards))

            # 2. Verify ZAINE_AGENT=1 streams /run, updates HUD step/tool/queue, leaves /agent & /agents untouched,
            #    handles /runs listing & /stop cleanly
            os.environ["ZAINE_AGENT"] = "1"
            recorded_stream_args: List[Dict[str, Any]] = []
            cancel_calls: List[Dict[str, Any]] = []
            seen_agent_cmds: List[str] = []
            tool_active_evt = asyncio.Event()
            release_tool_evt = asyncio.Event()

            async def fake_stream_chat_events(
                message,
                base_url=None,
                client_id="terminal-ui",
                request_id=None,
                default_first_token_timeout=60.0,
                idle_gap_timeout=30.0,
                client=None,
                force_autonomous=False,
                resume_run_id=None,
            ):
                recorded_stream_args.append({
                    "message": message,
                    "force_autonomous": force_autonomous,
                    "resume_run_id": resume_run_id,
                })
                yield {"type": "queued", "position": 2}
                await asyncio.sleep(0)
                yield {"type": "running"}
                yield {"type": "tool_event", "stage": "agent", "tool": "zaine-jarvis", "data": {
                    "agent_id": "zaine-jarvis", "display_name": "J.A.R.V.I.S.", "title": "Planner", "reason": "autonomy", "color": "#00f5a0", "source": "auto",
                }}
                yield {"type": "tool_event", "stage": "plan_start", "tool": "loop", "data": {"run_id": "RUN-TUI-1", "max_steps": 5}}
                yield {"type": "tool_event", "stage": "step", "tool": "zaine-coder", "data": {"run_id": "RUN-TUI-1", "step": 2, "max_steps": 5, "phase": "act"}}
                yield {"type": "tool_event", "stage": "start", "tool": "write_file", "data": {"path": "calc.py"}}
                if not resume_run_id:
                    tool_active_evt.set()
                    await release_tool_evt.wait()
                yield {"type": "tool_event", "stage": "done", "tool": "write_file", "data": "Wrote calc.py"}
                yield {"type": "token", "content": "Workspace task finished."}
                yield {
                    "type": "done",
                    "reply": "Workspace task finished.",
                    "agent_run": {"run_id": "RUN-TUI-1", "status": "completed", "steps_executed": 2, "max_steps": 5},
                }

            async def fake_get_runs(resumable_only=False, base_url=None):
                return {
                    "ok": True,
                    "agent_enabled": True,
                    "runs": [{
                        "run_id": "RUN-CRASH-42",
                        "agent_id": "zaine-jarvis",
                        "status": "running",
                        "effective_status": "interrupted (resumable)",
                        "resumable": True,
                        "completed_steps": 2,
                        "max_steps": 6,
                        "updated_at": "2026-11-12T01:00:00",
                        "task": "Write script & verify",
                    }],
                }

            async def fake_cancel(request_id="", base_url=None, run_id=""):
                cancel_calls.append({"request_id": request_id, "run_id": run_id})
                return {"ok": True, "cancelled_runs": 1, "status": "cancelled"}

            app = ZaineTUI()
            orig_agent_handler = app.handle_agent_command

            def wrapped_agent_cmd(user_text: str):
                seen_agent_cmds.append(user_text)
                return None

            with (
                patch.object(tui_app_mod, "stream_chat_events", fake_stream_chat_events),
                patch.object(tui_app_mod, "get_runs", fake_get_runs),
                patch.object(tui_app_mod, "cancel_chat_request", fake_cancel),
                patch.object(app, "handle_agent_command", wrapped_agent_cmd),
            ):
                async with app.run_test(size=(150, 42)) as pilot:
                    hud = app.query_one(AgentStateHUD)
                    self.assertTrue(callable(orig_agent_handler))

                    # Untouched /agent & /agents routing still hits handle_agent_command
                    app._dispatch_user_turn("/agents")
                    app._dispatch_user_turn("/agent edith")
                    self.assertEqual(seen_agent_cmds, ["/agents", "/agent edith"])

                    # /run <goal> launches autonomous stream and updates HUD live
                    app._dispatch_user_turn("/run Create calc.py and test it")
                    await asyncio.wait_for(tool_active_evt.wait(), timeout=3.0)
                    await pilot.pause(0.01)
                    self.assertEqual(hud.step_display, "2/5")
                    self.assertEqual(hud.tool_in_use, "write_file")
                    self.assertEqual(hud.run_id, "RUN-TUI-1")
                    self.assertEqual(hud.queue_display, "0 queued (1 active)")

                    release_tool_evt.set()
                    await pilot.pause(0.05)
                    self.assertEqual(hud.tool_in_use, "n/a")
                    self.assertEqual(hud.run_status, "completed")
                    self.assertEqual(hud.agent_name, "J.A.R.V.I.S.")
                    self.assertTrue(recorded_stream_args[-1]["force_autonomous"])
                    self.assertEqual(recorded_stream_args[-1]["message"], "Create calc.py and test it")

                    # /runs lists interrupted scratchpad & resume hint
                    app._dispatch_user_turn("/runs")
                    await pilot.pause(0.1)
                    assistant_texts = [c.markdown_text for c in app.query(AssistantTurnCard)]
                    self.assertTrue(any("RUN-CRASH-42" in t and "interrupted (resumable)" in t for t in assistant_texts))

                    # /run --resume <id> triggers resume_run_id forwarding
                    app._dispatch_user_turn("/run --resume RUN-CRASH-42")
                    await pilot.pause(0.2)
                    self.assertEqual(recorded_stream_args[-1]["resume_run_id"], "RUN-CRASH-42")

                    # /stop calls cancel_chat_request cleanly & shows RUN STOPPED card
                    app._dispatch_user_turn("/stop")
                    await pilot.pause(0.1)
                    self.assertGreaterEqual(len(cancel_calls), 1)
                    self.assertTrue(any("RUN STOPPED" in c.title_text for c in app.query(SystemCard)))
        finally:
            if orig_env is None:
                os.environ.pop("ZAINE_AGENT", None)
            else:
                os.environ["ZAINE_AGENT"] = orig_env
