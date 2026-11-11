"""Tests for Phase A autonomous loop (autonomy/), tool JSON validation, permission gating,
single-model lock, circuit breakers, timeouts, and instant cancellation.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _fake_stream(chunks: List[str], *, think_chunks: List[str] | None = None) -> Iterator[Dict[str, Any]]:
    """Builds Ollama-compatible streaming dict chunks for deterministic tests."""
    if think_chunks:
        yield {"message": {"content": "<think>"}, "done": False}
        for th in think_chunks:
            yield {"message": {"content": th}, "done": False}
        yield {"message": {"content": "</think>"}, "done": False}
    for tok in chunks:
        yield {"message": {"content": tok}, "done": False}
    yield {
        "message": {"content": ""},
        "done": True,
        "prompt_eval_count": 42,
        "eval_count": 18,
    }


def test_flag_off_preserves_legacy_behavior(monkeypatch):
    """When ZAINE_AGENT is unset or 0, is_agent_enabled() is False and AutonomousLoop is bypassed."""
    from autonomy import is_agent_enabled
    import autonomy.loop as loop_mod

    monkeypatch.delenv("ZAINE_AGENT", raising=False)
    assert is_agent_enabled() is False
    monkeypatch.setenv("ZAINE_AGENT", "0")
    assert is_agent_enabled() is False

    called = {"autonomous_init": False}

    class _SpyLoop:
        def __init__(self, *args, **kwargs):
            called["autonomous_init"] = True

    monkeypatch.setattr(loop_mod, "AutonomousLoop", _SpyLoop)

    import agent as agent_mod
    import core_service

    cfg = core_service.core_runtime_config()
    assert cfg["agent_enabled"] is False

    # Build lightweight ZaineAgent without pinning real Ollama VRAM in constructor
    monkeypatch.setattr(agent_mod.router, "pin_reflex_in_vram", lambda: None)
    monkeypatch.setattr(agent_mod.ZaineAgent, "memory", None, raising=False)

    class _MemStub:
        def __init__(self):
            self.msgs = []

        def add(self, role, content):
            self.msgs.append({"role": role, "content": content})

        def get_messages(self):
            return list(self.msgs)

        def get_persistent_context(self, current_prompt=""):
            return ""

    z = agent_mod.ZaineAgent()
    z.memory = _MemStub()

    # Stub legacy streaming requests.post so legacy chat_stream finishes cleanly without Ollama
    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield json.dumps({"message": {"content": "Legacy reply ready."}, "done": False}).encode()
            yield json.dumps({"message": {"content": ""}, "done": True, "prompt_eval_count": 5, "eval_count": 4}).encode()

    monkeypatch.setattr(agent_mod.requests, "post", lambda *a, **kw: _FakeResp())
    monkeypatch.setattr(agent_mod.router, "get_instant_acknowledgment", lambda *a, **kw: "")

    out = list(z.chat_stream("say hello cleanly"))
    assert "Legacy reply ready." in " ".join(out)
    assert called["autonomous_init"] is False


def test_plan_act_observe_reflect_sse_and_completion():
    """Full Plan -> Act -> Observe -> Reflect cycle emits live SSE events and creates artifact."""
    from autonomy.loop import AutonomousLoop, LoopConfig
    from core.circuit_breaker import CircuitBreakerManager

    responses = iter([
        json.dumps({"steps": ["Write greeting script", "Verify script output"], "direct": False}),
        json.dumps({"tool": "write_workspace_file", "args": {"filepath": "hello_demo.py", "content": "print('hi')"}}),
        "Created hello_demo.py and confirmed its contents.",
    ])

    def model_stream(payload, cancel_token, timeout_s):
        text = next(responses)
        return _fake_stream([text], think_chunks=["Evaluating next step."])

    executed: List[Dict[str, Any]] = []

    def tool_exec(tc: Dict[str, Any]) -> str:
        executed.append(tc)
        return "Successfully wrote 'hello_demo.py' (11 bytes)."

    events: List[Tuple[str, str, Any]] = []
    cb = CircuitBreakerManager(failure_threshold=3)
    loop = AutonomousLoop(
        config=LoopConfig(max_steps=4, wall_clock_timeout_s=30.0),
        model_stream_fn=model_stream,
        tool_exec_fn=tool_exec,
        breaker=cb,
        on_event=lambda stage, tool, data: events.append((stage, tool, data)),
    )

    res = loop.run("Create hello_demo.py and report back")
    assert res.status == "completed"
    assert res.plan == ["Write greeting script", "Verify script output"]
    assert res.steps_executed == 2
    assert "hello_demo.py" in res.artifacts
    assert "Created hello_demo.py" in res.summary
    assert len(executed) == 1
    assert executed[0]["tool"] == "write_workspace_file"

    stages = [e[0] for e in events]
    for expected_stage in ("plan_start", "plan", "step", "think", "start", "done", "observe", "reflect"):
        assert expected_stage in stages


def test_hard_max_steps_and_wall_clock_timeout():
    """Loop enforces hard max_steps budget and wall-clock timeout cleanly."""
    from autonomy.loop import AutonomousLoop, LoopConfig
    from core.circuit_breaker import CircuitBreakerManager

    # Case 1: Hard max_steps budget = 2 (model keeps calling distinct tools)
    step_num = {"n": 0}

    def endless_tool_model(payload, cancel_token, timeout_s):
        step_num["n"] += 1
        if step_num["n"] == 1:
            return _fake_stream([json.dumps({"steps": ["Keep probing"], "direct": False})])
        return _fake_stream([json.dumps({"tool": "list_workspace_files", "args": {"idx": step_num["n"]}})])

    loop_steps = AutonomousLoop(
        config=LoopConfig(max_steps=2, wall_clock_timeout_s=30.0, no_progress_limit=5),
        model_stream_fn=endless_tool_model,
        tool_exec_fn=lambda tc: f"ok-{tc['args']['idx']}",
        breaker=CircuitBreakerManager(failure_threshold=5),
    )
    res_steps = loop_steps.run("Keep working until done")
    assert res_steps.status == "stopped_max_steps"
    assert res_steps.steps_executed == 2
    assert "step budget" in res_steps.stop_reason.lower()

    # Case 2: Tight wall-clock timeout
    def slow_model(payload, cancel_token, timeout_s):
        time.sleep(0.25)
        yield {"message": {"content": "still thinking"}, "done": True}

    loop_timeout = AutonomousLoop(
        config=LoopConfig(max_steps=5, wall_clock_timeout_s=0.12),
        model_stream_fn=slow_model,
        tool_exec_fn=lambda tc: "ok",
        breaker=CircuitBreakerManager(failure_threshold=5),
    )
    res_timeout = loop_timeout.run("Slow goal")
    assert res_timeout.status == "stopped_timeout"
    assert "timeout" in res_timeout.stop_reason.lower()


def test_circuit_breaker_three_identical_failing_calls():
    """3 identical failing tool calls trip the circuit breaker and report clearly."""
    from autonomy.loop import AutonomousLoop, LoopConfig
    from core.circuit_breaker import CircuitBreakerManager

    call_idx = {"n": 0}

    def repeat_fail_model(payload, cancel_token, timeout_s):
        call_idx["n"] += 1
        if call_idx["n"] == 1:
            return _fake_stream([json.dumps({"steps": ["Run script"], "direct": False})])
        return _fake_stream([json.dumps({"tool": "run_python_script", "args": {"script_path": "broken.py"}})])

    events: List[Tuple[str, str, Any]] = []
    cb = CircuitBreakerManager(failure_threshold=5)
    loop = AutonomousLoop(
        config=LoopConfig(max_steps=6, identical_failure_limit=3, no_progress_limit=10),
        model_stream_fn=repeat_fail_model,
        tool_exec_fn=lambda tc: "Error running tool 'run_python_script': SyntaxError line 1",
        breaker=cb,
        on_event=lambda s, t, d: events.append((s, t, d)),
    )

    res = loop.run("Run broken.py")
    assert res.status == "stopped_circuit_breaker"
    assert "3" in res.stop_reason or "repeated" in res.stop_reason.lower()
    assert "circuit_breaker" in [e[0] for e in events]


def test_circuit_breaker_no_progress_n_steps():
    """Repeating duplicate / no-progress results for N steps trips the circuit breaker."""
    from autonomy.loop import AutonomousLoop, LoopConfig
    from core.circuit_breaker import CircuitBreakerManager

    # Case 1: Exact identical repeated no-op calls trip stuck loop breaker
    call_idx = {"n": 0}

    def repeat_noop_model(payload, cancel_token, timeout_s):
        call_idx["n"] += 1
        if call_idx["n"] == 1:
            return _fake_stream([json.dumps({"steps": ["Inspect repeatedly"], "direct": False})])
        return _fake_stream([json.dumps({"tool": "list_workspace_files", "args": {"page": 1}})])

    loop_dup = AutonomousLoop(
        config=LoopConfig(max_steps=8, no_progress_limit=3, identical_failure_limit=10),
        model_stream_fn=repeat_noop_model,
        tool_exec_fn=lambda tc: "Files in workspace: empty.",
        breaker=CircuitBreakerManager(failure_threshold=5),
    )

    res_dup = loop_dup.run("Check workspace")
    assert res_dup.status == "stopped_circuit_breaker"
    assert res_dup.steps_executed == 3

    # Case 2: Varying args returning errors (zero forward progress across N=3 consecutive steps)
    step_idx = {"n": 0}

    def stagnant_var_model(payload, cancel_token, timeout_s):
        step_idx["n"] += 1
        if step_idx["n"] == 1:
            return _fake_stream([json.dumps({"steps": ["Try files"], "direct": False})])
        return _fake_stream([json.dumps({"tool": "read_workspace_file", "args": {"filepath": f"missing_{step_idx['n']}.py"}})])

    loop_noprog = AutonomousLoop(
        config=LoopConfig(max_steps=8, no_progress_limit=3, identical_failure_limit=10),
        model_stream_fn=stagnant_var_model,
        tool_exec_fn=lambda tc: f"Error: file '{tc['args']['filepath']}' not found.",
        breaker=CircuitBreakerManager(failure_threshold=10),
    )
    res_noprog = loop_noprog.run("Read non-existent files")
    assert res_noprog.status == "stopped_circuit_breaker"
    assert "no progress" in res_noprog.stop_reason.lower()
    assert res_noprog.steps_executed == 3


def test_malformed_json_repair_once_and_single_retry_no_loop():
    """Validates deterministic 1-pass repair, at most 1 retry prompt, and clean failure without looping."""
    from autonomy.loop import AutonomousLoop, LoopConfig
    from autonomy.tool_validation import validate_and_repair_tool_calls
    from core.circuit_breaker import CircuitBreakerManager

    # 1. Single-pass deterministic repairs (no extra LLM call needed)
    fenced = '```json\n{"tool": "write_workspace_file", "args": {"filepath": "a.py", "content": "x=1",},}\n```'
    r1 = validate_and_repair_tool_calls(fenced)
    assert r1.status == "repaired"
    assert r1.calls == [{"tool": "write_workspace_file", "args": {"filepath": "a.py", "content": "x=1"}}]

    pseudo = '[TOOL] list_workspace_files, {"folder": "."}'
    r2 = validate_and_repair_tool_calls(pseudo)
    assert r2.status == "repaired"
    assert r2.calls == [{"tool": "list_workspace_files", "args": {"folder": "."}}]

    dirty_tail = '{"tool": "list_workspace_files", "args": {}} trailing non-json chatter'
    assert validate_and_repair_tool_calls(dirty_tail, strict_only=True).status == "needs_retry"

    # 2. Unrepairable broken JSON -> 1 retry recovers cleanly
    seq_recover = iter([
        json.dumps({"steps": ["Create note"], "direct": False}),
        '{"tool": "write_workspace_file", "args": {"filepath": UNQUOTED BROKEN ===',
        json.dumps({"tool": "write_workspace_file", "args": {"filepath": "fixed.txt", "content": "ok"}}),
        "Done writing fixed.txt.",
    ])
    loop_recover = AutonomousLoop(
        config=LoopConfig(max_steps=4),
        model_stream_fn=lambda p, c, t: _fake_stream([next(seq_recover)]),
        tool_exec_fn=lambda tc: "Wrote fixed.txt",
        breaker=CircuitBreakerManager(),
    )
    res_recover = loop_recover.run("Write fixed.txt")
    assert res_recover.status == "completed"
    assert res_recover.usage["model_calls"] == 4  # 1 plan + 1 broken act + 1 retry + 1 final

    # 3. Persistently broken JSON after retry -> fails cleanly with <=2 calls in step 1 (no loop)
    broken_calls = {"count": 0}

    def always_broken(payload, cancel_token, timeout_s):
        broken_calls["count"] += 1
        if broken_calls["count"] == 1:
            return _fake_stream([json.dumps({"steps": ["Attempt action"], "direct": False})])
        return _fake_stream(['{"tool": "write_workspace_file", "args": BROKEN{{{'])

    loop_fail = AutonomousLoop(
        config=LoopConfig(max_steps=5),
        model_stream_fn=always_broken,
        tool_exec_fn=lambda tc: "should_not_run",
        breaker=CircuitBreakerManager(),
    )
    res_fail = loop_fail.run("Trigger broken JSON")
    assert res_fail.status == "failed_validation"
    assert res_fail.usage["model_calls"] == 3  # 1 plan + 1 initial act + 1 retry max
    assert broken_calls["count"] == 3


def test_alias_resolution_permission_enforcement(monkeypatch):
    """When ZAINE_AGENT=1, aliases resolve before agent_profile.allows() and is_tool_permitted() on EVERY route."""
    import agents
    import agent as agent_mod
    from agents.registry import AgentSelection
    from autonomy.loop import AutonomousLoop, LoopConfig
    from core.circuit_breaker import CircuitBreakerManager

    monkeypatch.setenv("ZAINE_AGENT", "1")

    assert agent_mod.resolve_tool_alias("run_shell") == "execute_command"
    assert agent_mod.resolve_tool_alias("write-file") == "write_workspace_file"
    assert agent_mod.resolve_tool_alias("ask_subagent") == "ask_agent"
    assert agent_mod.resolve_tool_alias("manga_recap") == "generate_manga_recap"

    monkeypatch.setattr(agent_mod.router, "pin_reflex_in_vram", lambda: None)
    z = agent_mod.ZaineAgent()
    vision_profile = agents.get_registry().resolve("vision")
    z.active_agent = vision_profile
    # Simulate keyword auto-routing (not explicit @mention) — MUST STILL enforce when ZAINE_AGENT=1!
    z.last_agent_selection = AgentSelection(profile=vision_profile, source="route", reason="test", message="analyze screen")

    ran = {"exec": False, "write": False}
    monkeypatch.setitem(agent_mod.TOOL_REGISTRY, "execute_command", lambda **kw: ran.update({"exec": True}) or "ran")
    monkeypatch.setitem(agent_mod.TOOL_REGISTRY, "write_workspace_file", lambda **kw: ran.update({"write": True}) or "wrote")

    denial_shell = z._execute_tool({"tool": "run_shell", "args": {"command": "echo oops"}})
    assert "outside" in denial_shell.lower() or "denied" in denial_shell.lower() or "permission" in denial_shell.lower()
    assert ran["exec"] is False

    denial_write = z._execute_tool({"tool": "write_file", "args": {"filepath": "x.py", "content": "1"}})
    assert "outside" in denial_write.lower() or "denied" in denial_write.lower() or "permission" in denial_write.lower()
    assert ran["write"] is False

    denial_enroll = z._execute_tool({"tool": "enroll_face", "args": {"name": "intruder"}})
    assert "outside" in denial_enroll.lower() or "denied" in denial_enroll.lower()

    # Also verify AutonomousLoop._check_tool_permission blocks aliased disallowed tools before calling tool_exec_fn
    called_exec = {"count": 0}
    responses = iter([
        json.dumps({"steps": ["Attempt disallowed shell alias"], "direct": False}),
        json.dumps({"tool": "run_shell", "args": {"command": "whoami"}}),
        "Aborted disallowed shell call.",
    ])
    loop = AutonomousLoop(
        config=LoopConfig(max_steps=3),
        profile=vision_profile,
        model_stream_fn=lambda p, c, t: _fake_stream([next(responses)]),
        tool_exec_fn=lambda tc: called_exec.update({"count": called_exec["count"] + 1}) or "ran",
        tool_alias_fn=agent_mod.resolve_tool_alias,
        breaker=CircuitBreakerManager(),
    )
    res = loop.run("Run whoami")
    assert called_exec["count"] == 0
    assert res.tool_history[0]["tool"] == "execute_command"
    assert res.tool_history[0]["status"] == "denied"


def test_instant_cancel_via_token_and_api_chat_cancel(monkeypatch):
    """Hanging HTTP/Ollama stream aborts in <1s when cancelled via cancel_run / Coordinator."""
    from autonomy.loop import AutonomousLoop, LoopConfig, cancel_run
    import autonomy.loop as loop_mod
    from core.circuit_breaker import CircuitBreakerManager

    started = threading.Event()
    release_server = threading.Event()

    class _HangingHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0") or 0)
            _ = self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            first = json.dumps({"message": {"content": "working... "}, "done": False}).encode() + b"\n"
            self.wfile.write(first)
            self.wfile.flush()
            started.set()
            # Stall until test cleans up or client socket closes
            release_server.wait(timeout=5.0)

        def log_message(self, fmt, *args):
            return None

    server = HTTPServer(("127.0.0.1", 0), _HangingHandler)
    port = server.server_address[1]
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()

    monkeypatch.setattr(loop_mod, "OLLAMA_URL", f"http://127.0.0.1:{port}/api/chat")

    result_box: Dict[str, Any] = {}
    loop = AutonomousLoop(
        config=LoopConfig(max_steps=3, wall_clock_timeout_s=15.0, request_timeout_s=15.0),
        breaker=CircuitBreakerManager(),
        request_id="REQ-CANCEL-TEST",
    )

    def _run():
        result_box["res"] = loop.run("Goal that hangs on Ollama")

    t0 = time.monotonic()
    runner = threading.Thread(target=_run, daemon=True)
    runner.start()
    assert started.wait(timeout=3.0)

    cancelled_count = cancel_run("REQ-CANCEL-TEST")
    assert cancelled_count >= 1

    runner.join(timeout=2.0)
    elapsed = time.monotonic() - t0
    release_server.set()
    server.shutdown()
    server.server_close()

    assert not runner.is_alive()
    assert result_box["res"].status == "cancelled"
    assert elapsed < 2.0


def test_single_model_lock_on_deep_code(monkeypatch):
    """When ZAINE_AGENT=1 and ZAINE_SINGLE_MODEL=1, DEEP_CODE keeps zaine-reflex-7b (never coder-7b)."""
    import agent as agent_mod
    import autonomy.loop as loop_mod
    from autonomy.loop import LoopResult

    monkeypatch.setenv("ZAINE_AGENT", "1")
    monkeypatch.setenv("ZAINE_SINGLE_MODEL", "1")
    monkeypatch.setenv("ZAINE_AGENT_MODEL", "zaine-reflex-7b")
    assert agent_mod.router.single_model is True
    monkeypatch.setattr(agent_mod.router, "pin_reflex_in_vram", lambda: None)
    monkeypatch.setattr(agent_mod.router, "resolve_model", lambda m: m)

    seen_models: List[str] = []

    class _CaptureLoop:
        def __init__(self, *, config=None, **kwargs):
            seen_models.append(config.model_name if config else "")
            self._last_model_calls = [{"model": config.model_name, "prompt_eval_count": 10, "eval_count": 5}]

        def run(self, goal, **kwargs):
            return LoopResult(run_id="RUN-TEST", status="completed", summary="Code ready.")

    monkeypatch.setattr(loop_mod, "AutonomousLoop", _CaptureLoop)

    class _MemStub:
        def __init__(self):
            self.msgs = []

        def add(self, role, content):
            self.msgs.append({"role": role, "content": content})

        def get_messages(self):
            return list(self.msgs)

        def get_persistent_context(self, current_prompt=""):
            return ""

    z = agent_mod.ZaineAgent()
    z.memory = _MemStub()

    # Prompt specifically hitting DEEP_CODE tier ("debug python traceback refactor")
    out = list(z.chat_stream("Refactor this python module and debug the traceback"))
    assert "Code ready." in out[0]
    assert seen_models == ["zaine-reflex-7b"]


def test_core_service_sse_and_cancel_endpoint(monkeypatch):
    """Verifies /api/chat/stream emits agent_run telemetry and /api/chat/cancel aborts live loop."""
    from http.server import ThreadingHTTPServer
    import requests
    import core_service
    from autonomy.loop import AutonomousLoop, LoopConfig, LoopResult
    from core.circuit_breaker import CircuitBreakerManager

    monkeypatch.setenv("ZAINE_AGENT", "1")
    monkeypatch.setenv("ZAINE_SINGLE_MODEL", "1")

    gate_started = threading.Event()
    gate_release = threading.Event()

    class _StubAgent:
        def __init__(self):
            self.last_tool_called = None
            self.ultron_mode = False
            self.last_agent_selection = None
            self.last_turn_calls = []
            self.last_loop_result = None

        def chat_stream(self, user_msg, on_tool_event=None, cancel_check=None, request_id=None):
            if "hang" in user_msg.lower():
                def slow_model(payload, cancel_token, timeout_s):
                    gate_started.set()
                    while not cancel_token.cancelled and not gate_release.is_set():
                        cancel_token.wait(timeout=0.05)
                    yield {"message": {"content": ""}, "done": True}

                loop = AutonomousLoop(
                    config=LoopConfig(max_steps=3, wall_clock_timeout_s=10.0),
                    model_stream_fn=slow_model,
                    tool_exec_fn=lambda tc: "ok",
                    breaker=CircuitBreakerManager(),
                    request_id=request_id,
                    cancel_check=cancel_check,
                    on_event=on_tool_event,
                )
                res = loop.run(user_msg)
                self.last_loop_result = res
                yield res.summary
                return

            if on_tool_event:
                on_tool_event("plan_start", "loop", {"run_id": "RUN-SSE1"})
                on_tool_event("plan", "loop", {"run_id": "RUN-SSE1", "steps": ["Check files"]})
            self.last_loop_result = LoopResult(
                run_id="RUN-SSE1",
                status="completed",
                summary="SSE completed cleanly.",
                plan=["Check files"],
                steps_executed=1,
                max_steps=6,
                stop_reason="completed",
                elapsed_s=0.05,
            )
            yield "SSE completed cleanly."

    class _StubCore:
        auth_token = "test-token-123"
        warming = False
        current_mode = "jarvis"
        current_status = "idle"
        port = 0

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

    headers = {"X-Zaine-Token": "test-token-123", "Content-Type": "application/json"}
    base = f"http://127.0.0.1:{port}"
    try:
        # 1. Verify /api/chat/stream delivers live tool_event + agent_run on done
        resp = requests.post(
            f"{base}/api/chat/stream",
            headers=headers,
            json={"message": "Check status"},
            stream=True,
            timeout=5.0,
        )
        assert resp.status_code == 200
        frames = []
        for raw in resp.iter_lines(decode_unicode=True):
            if raw and raw.startswith("data: "):
                frames.append(json.loads(raw[6:]))
        resp.close()

        types = [f.get("type") for f in frames]
        assert "tool_event" in types
        assert "done" in types
        done_frame = [f for f in frames if f.get("type") == "done"][-1]
        assert done_frame["agent_run"]["run_id"] == "RUN-SSE1"
        assert done_frame["agent_run"]["status"] == "completed"

        # 2. Verify /api/chat/cancel aborts a running autonomous loop immediately
        cancel_frames: List[Dict[str, Any]] = []
        stream_done = threading.Event()

        def _stream_hang():
            r = requests.post(
                f"{base}/api/chat/stream",
                headers=headers,
                json={"message": "Please hang until cancelled", "request_id": "REQ-HTTP-CANCEL"},
                stream=True,
                timeout=8.0,
            )
            for raw in r.iter_lines(decode_unicode=True):
                if raw and raw.startswith("data: "):
                    cancel_frames.append(json.loads(raw[6:]))
            r.close()
            stream_done.set()

        st = threading.Thread(target=_stream_hang, daemon=True)
        st.start()
        assert gate_started.wait(timeout=3.0)

        t_cancel = time.monotonic()
        c_resp = requests.post(
            f"{base}/api/chat/cancel",
            headers=headers,
            json={"request_id": "REQ-HTTP-CANCEL"},
            timeout=3.0,
        )
        assert c_resp.status_code == 200
        assert stream_done.wait(timeout=2.5)
        assert time.monotonic() - t_cancel < 2.5
        assert srv.core_service_instance.agent.last_loop_result.status == "cancelled"
    finally:
        gate_release.set()
        srv.shutdown()
        srv.server_close()

