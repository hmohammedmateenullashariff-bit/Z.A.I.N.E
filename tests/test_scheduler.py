"""
tests/test_scheduler.py
Phase E verification tests:
- Gating behind ZAINE_AGENT=1 (ZAINE_AGENT=0 leaves scheduler idle & legacy behavior untouched)
- Schedule types (background, once, interval, daily) + cancellation
- Sequential execution via RequestCoordinator (single-GPU mutual exclusion)
- Durable delivery to Obsidian dev vault (PROVISIONAL trust, LOCAL_ONLY taint) + Telegram
- Global quiet mode suppressing Telegram pushes, approval pings, and Heartbeat alerts
- Unattended risky actions pause for human ApprovalRegistry verdict (never auto-approve) and resume cleanly
- Authenticated CoreService /api/scheduler, /api/quiet, and TUI /schedule + /quiet + /run --bg commands
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import approval as approval_mod
import core_service
import coordinator as coordinator_mod
import db.engine as db_engine
import memory
import memory_manager as mm_mod
from autonomy.audit import AuditLogStore
from autonomy.loop import AutonomousLoop, LoopConfig
from autonomy.scheduler import (
    GoalScheduler,
    SchedulerStore,
    compute_next_daily_run,
    get_quiet_status,
    is_quiet_mode,
    set_quiet_mode,
)
from autonomy.scratchpad import RunScratchpadStore
from core.circuit_breaker import CircuitBreakerManager
from tui.widgets.chat import AssistantTurnCard, SystemCard


def _stream_factory(responses: List[str], *, concurrency_counter: Dict[str, int] | None = None):
    """Builds a deterministic scripted Ollama stream with optional overlap instrumentation."""
    idx = {"i": 0}

    def _stream(payload: Dict[str, Any], cancel_token: Any, timeout_s: float) -> Iterator[Dict[str, Any]]:
        if concurrency_counter is not None:
            concurrency_counter["active"] += 1
            concurrency_counter["max"] = max(concurrency_counter["max"], concurrency_counter["active"])
        try:
            time.sleep(0.02)
            i = idx["i"]
            idx["i"] += 1
            text = responses[i] if i < len(responses) else "Done."
            yield {"message": {"content": text}, "done": False}
            yield {
                "done": True,
                "load_duration": 0,
                "prompt_eval_count": 20,
                "prompt_eval_duration": 1000,
                "eval_count": 10,
                "eval_duration": 1000,
            }
        finally:
            if concurrency_counter is not None:
                concurrency_counter["active"] -= 1

    return _stream


@pytest.fixture()
def scheduler_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vault_dir = tmp_path / "dev_vault"
    vault_dir.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "zaine_sched.db"
    approvals_db = tmp_path / "zaine_approvals.db"
    runs_dir = tmp_path / "runs"
    audit_dir = tmp_path / "audit"
    sched_dir = tmp_path / "scheduler"
    ws_dir = tmp_path / "workspace"
    for d in (runs_dir, audit_dir, sched_dir, ws_dir):
        d.mkdir(parents=True, exist_ok=True)

    test_eng = db_engine.DatabaseEngine(db_path=db_file)
    monkeypatch.setenv("ZAINE_AGENT", "1")
    monkeypatch.setenv("ZAINE_SINGLE_MODEL", "1")
    monkeypatch.setenv("ZAINE_OBSIDIAN_VAULT_PATH", str(vault_dir))
    monkeypatch.setenv("ZAINE_RUNS_DIR", str(runs_dir))
    monkeypatch.setenv("ZAINE_AUDIT_DIR", str(audit_dir))
    monkeypatch.setenv("ZAINE_SCHEDULER_DIR", str(sched_dir))
    monkeypatch.setenv("ZAINE_WORKSPACE", str(ws_dir))
    monkeypatch.delenv("ZAINE_QUIET_MODE", raising=False)
    monkeypatch.setattr(memory, "DB_PATH", db_file)
    monkeypatch.setattr(db_engine, "get_db_engine", lambda: test_eng)
    monkeypatch.setattr(approval_mod, "DB_PATH", approvals_db)
    mm_mod._manager_instance = None

    import autonomy.scheduler as sched_mod
    sched_mod._DEFAULT_SCHEDULER = None

    yield {
        "vault_dir": vault_dir,
        "db_file": db_file,
        "approvals_db": approvals_db,
        "runs_dir": runs_dir,
        "audit_dir": audit_dir,
        "sched_dir": sched_dir,
        "ws_dir": ws_dir,
    }

    mm_mod._manager_instance = None
    sched_mod._DEFAULT_SCHEDULER = None


def test_scheduler_disabled_under_zaine_agent_zero(scheduler_env, monkeypatch: pytest.MonkeyPatch):
    """When ZAINE_AGENT=0, scheduler refuses to run pending jobs and leaves Telegram alert flow intact."""
    monkeypatch.setenv("ZAINE_AGENT", "0")
    called = {"n": 0}
    sched = GoalScheduler(store=SchedulerStore())
    job = sched.enqueue_background("Audit logs in workspace")

    def _boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("Loop must not run under ZAINE_AGENT=0")

    sched.set_loop_factory(_boom)
    assert sched.run_pending() == []
    assert sched.start() is False
    assert called["n"] == 0
    assert sched.get_job(job.job_id).status == "pending"

    # Legacy heartbeat cycle runs cleanly with ZAINE_AGENT=0 without invoking scheduler
    import heartbeat
    hb = heartbeat.HeartbeatDaemon()
    monkeypatch.setattr(hb, "check_reminders", lambda: 0)
    monkeypatch.setattr(hb, "check_battery", lambda: {})
    monkeypatch.setattr(hb, "check_morning_briefing", lambda: {})
    monkeypatch.setattr(hb, "check_evening_debrief", lambda: {})
    monkeypatch.setattr(hb, "check_disk_space", lambda: {})
    monkeypatch.setattr(hb, "check_ergonomics", lambda: {})
    monkeypatch.setattr(hb, "check_desk_presence_sentinel", lambda: {})
    monkeypatch.setattr(hb, "check_youtube_studio_schedule", lambda: {})
    monkeypatch.setattr(hb, "check_proactive_observation", lambda: {})
    hb.run_cycle()
    assert called["n"] == 0


def test_schedule_types_obsidian_vault_and_telegram_delivery(scheduler_env, monkeypatch: pytest.MonkeyPatch):
    """Scheduled background, interval, daily, and once jobs run due items and deliver to Obsidian + Telegram."""
    sent_alerts: List[str] = []
    monkeypatch.setattr("telegram_bridge.send_telegram_alert", lambda text, **kw: (sent_alerts.append(text), True)[1])

    sched = GoalScheduler(store=SchedulerStore())

    def _factory(job, req_id):
        stream_fn = _stream_factory([
            '{"steps": ["Analyze target", "Summarize"], "direct_answer_possible": true}',
            f"Completed goal: {job.goal}",
        ])
        return AutonomousLoop(
            config=LoopConfig(model_name="zaine-reflex-7b", max_steps=3),
            model_stream_fn=stream_fn,
            breaker=CircuitBreakerManager(),
            suppress_vault_flush=True,
        )

    sched.set_loop_factory(_factory)

    # 1. Background job runs immediately and creates exactly ONE Obsidian dev vault note + Telegram push
    bg_job = sched.enqueue_background("Check workspace inventory")
    outcomes = sched.run_pending()
    assert len(outcomes) == 1
    assert outcomes[0]["job_id"] == bg_job.job_id
    assert outcomes[0]["status"] == "completed"
    assert outcomes[0]["telegram_notified"] is True
    assert outcomes[0]["obsidian_note_id"]

    # Confirm single Obsidian note with LOCAL_ONLY & provisional trust in dev vault ONLY
    md_files = list(scheduler_env["vault_dir"].rglob("*.md"))
    assert len(md_files) == 1
    note_text = md_files[0].read_text(encoding="utf-8")
    assert "privacy_taint: LOCAL_ONLY" in note_text
    assert "trust: provisional" in note_text
    assert "[Background]" in note_text
    assert len(sent_alerts) == 1
    assert bg_job.job_id in sent_alerts[0]

    # Running pending again should NOT re-run completed background job
    assert sched.run_pending() == []

    # 2. Interval job reschedules forward cleanly and can be cancelled
    int_job = sched.add_job("Periodic health sweep", schedule_kind="interval", interval_seconds=30, run_immediately=True)
    res2 = sched.run_pending()
    assert len(res2) == 1
    refreshed = sched.get_job(int_job.job_id)
    assert refreshed.status == "pending"
    assert refreshed.enabled is True
    assert refreshed.run_count == 1
    assert refreshed.next_run_at != ""
    # Not due yet right after running
    assert sched.run_pending() == []
    # Future check triggers second interval run
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=40)
    res3 = sched.run_pending(now=future)
    assert len(res3) == 1
    assert sched.get_job(int_job.job_id).run_count == 2

    cancelled = sched.cancel_job(int_job.job_id)
    assert cancelled.status == "cancelled" and cancelled.enabled is False
    assert sched.run_pending(now=future + dt.timedelta(seconds=90)) == []

    # 3. Daily schedule computes valid future UTC timestamp from local HH:MM
    daily_job = sched.add_job("Daily status digest", schedule_kind="daily", daily_time="23:59")
    assert daily_job.next_run_at
    assert compute_next_daily_run("08:30", now_local=dt.datetime(2026, 6, 1, 9, 0).astimezone()) > dt.datetime(2026, 6, 1, 9, 0, tzinfo=dt.datetime.now().astimezone().tzinfo).astimezone(dt.timezone.utc)


def test_scheduler_serializes_with_request_coordinator(scheduler_env, monkeypatch: pytest.MonkeyPatch):
    """Background jobs queue behind active RequestCoordinator chat turns so GPU model calls never overlap."""
    monkeypatch.setattr("telegram_bridge.send_telegram_alert", lambda *a, **k: True)
    coord = coordinator_mod.get_request_coordinator()

    order: List[str] = []
    concurrency = {"active": 0, "max": 0}
    sched = GoalScheduler(store=SchedulerStore())
    sched.set_loop_factory(
        lambda job, req_id: AutonomousLoop(
            config=LoopConfig(model_name="zaine-reflex-7b", max_steps=2),
            model_stream_fn=_stream_factory(
                ['{"steps": ["Reply"], "direct_answer_possible": true}', "Serialized done."],
                concurrency_counter=concurrency,
            ),
            breaker=CircuitBreakerManager(),
            suppress_vault_flush=True,
        )
    )

    # Occupy coordinator slot with an interactive chat request
    st, m_req, _ = coord.claim_request(request_id="interactive-turn-1", client="tui")
    assert st == "claimed"
    assert m_req.state == "running"

    sched.enqueue_background("Queued background goal")
    t = threading.Thread(target=lambda: (sched.run_pending(), order.append("scheduler_done")), daemon=True)
    t.start()

    # Wait briefly to verify scheduler is waiting on RequestCoordinator, not executing yet
    time.sleep(0.15)
    assert "scheduler_done" not in order
    assert concurrency["max"] == 0

    order.append("interactive_done")
    coord.complete_request("interactive-turn-1", {"ok": True})
    t.join(timeout=5.0)

    assert order == ["interactive_done", "scheduler_done"]
    assert concurrency["max"] == 1


def test_global_quiet_mode_suppresses_telegram_approvals_and_heartbeat(scheduler_env, monkeypatch: pytest.MonkeyPatch):
    """Global quiet mode mutes Telegram alerts, approval pings, and Heartbeat alerts while logging a digest."""
    post_calls: List[Any] = []

    class _FakeResp:
        status_code = 200

    def _fake_post(*a, **k):
        post_calls.append((a, k))
        return _FakeResp()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "12345")
    monkeypatch.setattr("telegram_bridge.requests.post", _fake_post)

    set_quiet_mode(True, reason="Sleep hours")
    assert is_quiet_mode() is True

    # 1. Heartbeat sees global quiet mode
    import heartbeat
    hb = heartbeat.HeartbeatDaemon()
    assert hb.is_global_quiet() is True
    assert hb.is_quiet() is True
    assert hb.is_night_mode() is True

    # 2. Direct telegram_bridge.send_telegram_alert honors quiet mode unless force=True
    import telegram_bridge as tb
    assert tb.send_telegram_alert("Should be silenced") is False
    assert len(post_calls) == 0

    # 3. ApprovalRegistry suppresses noisy Telegram card while leaving PENDING proposal in SQLite
    pid = approval_mod.ApprovalRegistry.create_proposal(
        action_type="shell_exec",
        title="Run cleanup command",
        description="Needs approval",
        code_or_cmd="echo cleanup",
    )
    assert approval_mod.ApprovalRegistry.get_proposal(pid)["status"] == "PENDING"
    assert len(post_calls) == 0

    # 4. Scheduler suppresses Telegram delivery during quiet mode but still writes Obsidian vault note
    sched = GoalScheduler(store=SchedulerStore())
    sched.set_loop_factory(
        lambda job, req_id: AutonomousLoop(
            config=LoopConfig(model_name="zaine-reflex-7b", max_steps=2),
            model_stream_fn=_stream_factory(['{"steps": ["Check"], "direct_answer_possible": true}', "Quiet vault report."]),
            breaker=CircuitBreakerManager(),
            suppress_vault_flush=True,
        )
    )
    job = sched.enqueue_background("Quiet nightly audit")
    out = sched.run_pending()
    assert len(out) == 1
    assert out[0]["telegram_notified"] is False
    assert out[0]["obsidian_note_id"]
    assert len(post_calls) == 0

    qstat = get_quiet_status()
    assert qstat["enabled"] is True
    assert qstat["suppressed_count"] >= 3
    channels = {item["channel"] for item in qstat["digest"]}
    assert "telegram_scheduler" in channels
    assert "telegram_approval" in channels
    assert "telegram_alert" in channels

    # Turning quiet mode off restores notifications
    set_quiet_mode(False, reason="Morning")
    assert is_quiet_mode() is False
    job2 = sched.enqueue_background("Morning check")
    out2 = sched.run_pending()
    assert out2[0]["telegram_notified"] is True
    assert len(post_calls) == 1
    assert job2.job_id in str(post_calls[0])


def test_unattended_risky_action_pauses_and_resumes_only_after_human_approval(scheduler_env, monkeypatch: pytest.MonkeyPatch):
    """Unattended runs never auto-approve: they pause with PENDING SQLite proposal and resume only once APPROVED."""
    monkeypatch.setattr("telegram_bridge.send_telegram_alert", lambda *a, **k: True)
    executed_cmds: List[str] = []
    ext_target = scheduler_env["ws_dir"].parent / "outside_secret_ok" / "note.txt"
    ext_target.parent.mkdir(parents=True, exist_ok=True)

    # First run invokes execute_command (side effect), second resume produces final answer after tool executes
    model_responses = [
        '{"steps": ["Run shell check", "Report"], "direct_answer_possible": false}',
        '{"tool": "execute_command", "args": {"command": "echo safe_after_approval"}}',
        "Shell check executed after operator approval: ok.",
    ]
    shared_stream = _stream_factory(model_responses)

    def _tool_exec(tc: Dict[str, Any]) -> str:
        tname = tc.get("tool")
        args = tc.get("args") or {}
        if tname == "execute_command":
            executed_cmds.append(str(args.get("command") or ""))
            return "exit=0 stdout=safe_after_approval"
        return "ok"

    def _factory(job, req_id):
        return AutonomousLoop(
            config=LoopConfig(model_name="zaine-reflex-7b", max_steps=5),
            model_stream_fn=shared_stream,
            tool_exec_fn=_tool_exec,
            breaker=CircuitBreakerManager(),
            suppress_vault_flush=True,
        )

    sched = GoalScheduler(store=SchedulerStore())
    sched.set_loop_factory(_factory)
    job = sched.enqueue_background("Run diagnostic command and summarize")

    # 1. First tick MUST pause without executing execute_command
    res1 = sched.run_pending()
    assert len(res1) == 1
    assert res1[0]["status"] == "paused_approval"
    assert res1[0]["loop_status"] == "paused"
    pid = res1[0]["pending_approval_id"]
    assert pid.startswith("ACT-")
    assert executed_cmds == []  # CRITICAL: tool did NOT run!

    prop = approval_mod.ApprovalRegistry.get_proposal(pid)
    assert prop is not None
    assert prop["status"] == "PENDING"

    pad = RunScratchpadStore().load(res1[0]["run_id"])
    assert pad is not None
    assert pad.status == "paused"
    assert pad.resumable is True
    assert pad.pending_approval_id == pid
    assert pad.pending_tool == "execute_command"

    audit = AuditLogStore().load(res1[0]["run_id"])
    assert audit is not None
    assert any(a.get("decision") == "PAUSED_FOR_APPROVAL" and a.get("proposal_id") == pid for a in audit.approval_decisions)

    # 2. Second tick while still PENDING MUST NOT auto-approve or execute
    res_still_pending = sched.run_pending()
    assert res_still_pending == []
    assert executed_cmds == []
    # Even explicit manual resume() while PENDING refuses bypass
    loop_check = _factory(job, "check-req")
    pending_loop_res = loop_check.resume(pad.run_id)
    assert pending_loop_res.status == "paused"
    assert executed_cmds == []

    # 3. Operator approves proposal -> scheduler resumes and completes!
    ok, _ = approval_mod.ApprovalRegistry.approve(pid, note="Approved by operator")
    assert ok is True

    res2 = sched.run_pending()
    assert len(res2) == 1
    assert res2[0]["status"] == "completed"
    assert res2[0]["loop_status"] == "completed"
    assert executed_cmds == ["echo safe_after_approval"]

    final_job = sched.get_job(job.job_id)
    assert final_job.status == "completed"
    assert final_job.pending_approval_id == ""
    assert final_job.obsidian_note_id


def test_unattended_denied_approval_does_not_execute_tool(scheduler_env, monkeypatch: pytest.MonkeyPatch):
    """If an operator denies a paused proposal, resumed run records denial and never runs the risky tool."""
    monkeypatch.setattr("telegram_bridge.send_telegram_alert", lambda *a, **k: True)
    executed_cmds: List[str] = []
    shared_stream = _stream_factory([
        '{"steps": ["Run shell"], "direct_answer_possible": false}',
        '{"tool": "execute_command", "args": {"command": "rm -rf /tmp/never"}}',
        "Aborted command safely per operator denial.",
    ])

    sched = GoalScheduler(store=SchedulerStore())
    sched.set_loop_factory(
        lambda job, req_id: AutonomousLoop(
            config=LoopConfig(model_name="zaine-reflex-7b", max_steps=5),
            model_stream_fn=shared_stream,
            tool_exec_fn=lambda tc: (executed_cmds.append(str(tc)), "executed")[1],
            breaker=CircuitBreakerManager(),
            suppress_vault_flush=True,
        )
    )
    sched.enqueue_background("Run risky command")
    res1 = sched.run_pending()
    pid = res1[0]["pending_approval_id"]
    assert executed_cmds == []

    approval_mod.ApprovalRegistry.deny(pid, note="Too risky")
    res2 = sched.run_pending()
    assert res2[0]["status"] == "completed"
    assert executed_cmds == []


def test_unattended_delegated_pause_and_once_schedule(scheduler_env, monkeypatch: pytest.MonkeyPatch):
    """Paused approval inside a delegated subagent propagates to parent/scheduler and resumes cleanly after approval."""
    monkeypatch.setattr("telegram_bridge.send_telegram_alert", lambda *a, **k: True)
    fetched_urls: List[str] = []
    shared_stream = _stream_factory([
        '{"steps": ["Delegate health fetch"], "direct_answer_possible": false}',
        '{"tool": "delegate", "args": {"agent_id": "researcher", "task": "Fetch local health endpoint"}}',
        '{"steps": ["Browse local health"], "direct_answer_possible": false}',
        '{"tool": "browse_web", "args": {"url": "http://127.0.0.1:18080/health"}}',
        '{"steps": ["Browse local health"], "direct_answer_possible": false}',
        '{"tool": "browse_web", "args": {"url": "http://127.0.0.1:18080/health"}}',
        "Researcher fetched health status OK.",
        "Delegated diagnostic run completed after approval.",
    ])

    def _tool_exec(tc: Dict[str, Any]) -> str:
        if tc.get("tool") == "browse_web":
            url = str((tc.get("args") or {}).get("url") or "")
            fetched_urls.append(url)
            return f"status=200 from {url}"
        return "ok"

    sched = GoalScheduler(store=SchedulerStore())
    sched.set_loop_factory(
        lambda job, req_id: AutonomousLoop(
            config=LoopConfig(model_name="zaine-reflex-7b", max_steps=6),
            model_stream_fn=shared_stream,
            tool_exec_fn=_tool_exec,
            breaker=CircuitBreakerManager(),
            suppress_vault_flush=True,
        )
    )
    future_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=25)).isoformat()
    job = sched.add_job("Run delegated once task", schedule_kind="once", run_at=future_at)
    assert sched.run_pending() == []  # Not due yet

    res1 = sched.run_pending(now=dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30))
    assert len(res1) == 1
    assert res1[0]["status"] == "paused_approval"
    pid = res1[0]["pending_approval_id"]
    assert pid.startswith("ACT-")
    assert fetched_urls == []

    pad = RunScratchpadStore().load(res1[0]["run_id"])
    assert pad is not None and pad.pending_tool == "delegate"

    approval_mod.ApprovalRegistry.approve(pid, note="Allow delegated local fetch")
    res2 = sched.run_pending()
    assert len(res2) == 1
    assert res2[0]["status"] == "completed"
    assert fetched_urls == ["http://127.0.0.1:18080/health"]
    done_job = sched.get_job(job.job_id)
    assert done_job.status == "completed" and done_job.enabled is False


def test_default_build_loop_and_resume_observation_turn(scheduler_env, monkeypatch: pytest.MonkeyPatch):
    """Default GoalScheduler._build_loop imports cleanly and resumed runs inject approved observation turns."""
    monkeypatch.setattr("telegram_bridge.send_telegram_alert", lambda *a, **k: True)
    sched = GoalScheduler(store=SchedulerStore())
    job = sched.enqueue_background("Check system status")
    built = sched._build_loop(job, "req-default-build")
    assert isinstance(built, AutonomousLoop)
    assert built.profile is not None

    recorded_payloads: List[Dict[str, Any]] = []
    idx = {"i": 0}
    responses = [
        '{"steps": ["Run shell command"], "direct_answer_possible": false}',
        '{"tool": "execute_command", "args": {"command": "echo obs_ok"}}',
        "Command succeeded with obs_ok.",
    ]

    def _recording_stream(payload: Dict[str, Any], cancel_token: Any, timeout_s: float) -> Iterator[Dict[str, Any]]:
        recorded_payloads.append(payload)
        i = idx["i"]
        idx["i"] += 1
        text = responses[i] if i < len(responses) else "Done."
        yield {"message": {"content": text}, "done": False}
        yield {
            "done": True,
            "load_duration": 0,
            "prompt_eval_duration": 1000,
            "eval_duration": 1000,
            "prompt_eval_count": 20,
            "eval_count": 10,
        }

    sched.set_loop_factory(
        lambda j, req_id: AutonomousLoop(
            config=LoopConfig(model_name="zaine-reflex-7b", max_steps=5),
            model_stream_fn=_recording_stream,
            tool_exec_fn=lambda tc: "STDOUT:\nobs_ok",
            breaker=CircuitBreakerManager(),
            suppress_vault_flush=True,
        )
    )
    res1 = sched.run_pending()
    pid = res1[0]["pending_approval_id"]
    approval_mod.ApprovalRegistry.approve(pid, note="Approved")
    res2 = sched.run_pending()
    assert res2[0]["status"] == "completed"

    resume_msgs = recorded_payloads[-1]["messages"]
    joined = "\n".join(str(m.get("content", "")) for m in resume_msgs)
    assert "[OBSERVATION from approved 'execute_command'" in joined
    assert "obs_ok" in joined
    assert "Do NOT re-run 'execute_command'" in joined


def test_core_service_scheduler_and_quiet_endpoints(scheduler_env, monkeypatch: pytest.MonkeyPatch):
    """CoreService exposes X-Zaine-Token authenticated /api/scheduler, /api/quiet, and job endpoints."""
    monkeypatch.setattr("telegram_bridge.send_telegram_alert", lambda *a, **k: True)

    import autonomy.scheduler as sched_mod
    sched = sched_mod.get_goal_scheduler()
    sched.set_loop_factory(
        lambda job, req_id: AutonomousLoop(
            config=LoopConfig(model_name="zaine-reflex-7b", max_steps=2),
            model_stream_fn=_stream_factory(['{"steps": ["Reply"], "direct_answer_possible": true}', "HTTP triggered OK."]),
            breaker=CircuitBreakerManager(),
            suppress_vault_flush=True,
        )
    )

    class _StubCore:
        auth_token = "phase-e-token"
        warming = False
        current_mode = "jarvis"
        current_status = "idle"
        port = 0
        model_loaded = True
        agent = None

    srv = ThreadingHTTPServer(("127.0.0.1", 0), core_service.CoreServiceRequestHandler)
    srv.core_service_instance = _StubCore()
    port = srv.server_address[1]
    srv.core_service_instance.port = port
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    base = f"http://127.0.0.1:{port}"
    headers = {"X-Zaine-Token": "phase-e-token", "Content-Type": "application/json"}

    try:
        # 1. Auth required
        assert requests.get(f"{base}/api/scheduler", timeout=3).status_code == 401
        assert requests.post(f"{base}/api/quiet", json={"enabled": True}, timeout=3).status_code == 401

        # 2. Toggle quiet mode and verify /api/status reflects it
        q_on = requests.post(f"{base}/api/quiet", headers=headers, json={"enabled": True, "reason": "Focus"}, timeout=3)
        assert q_on.status_code == 200 and q_on.json()["quiet"]["enabled"] is True

        st = requests.get(f"{base}/api/status", headers=headers, timeout=3).json()
        assert st["quiet_mode"] is True

        # 3. Create background job, inspect /api/scheduler, trigger it, and cancel another
        created = requests.post(
            f"{base}/api/scheduler/jobs",
            headers=headers,
            json={"goal": "HTTP background summary", "schedule_kind": "background"},
            timeout=3,
        )
        assert created.status_code == 200
        job_id = created.json()["job"]["job_id"]

        listed = requests.get(f"{base}/api/scheduler", headers=headers, timeout=3).json()
        assert any(j["job_id"] == job_id for j in listed["jobs"])

        trig = requests.post(f"{base}/api/scheduler/jobs/{job_id}/trigger", headers=headers, json={}, timeout=5)
        assert trig.status_code == 200
        assert trig.json()["status"] == "completed"

        created2 = requests.post(
            f"{base}/api/scheduler/jobs",
            headers=headers,
            json={"goal": "Interval check", "schedule_kind": "interval", "interval_seconds": 120},
            timeout=3,
        )
        jid2 = created2.json()["job"]["job_id"]
        can = requests.post(f"{base}/api/scheduler/jobs/{jid2}/cancel", headers=headers, json={}, timeout=3)
        assert can.status_code == 200
        assert can.json()["job"]["status"] == "cancelled"
    finally:
        srv.shutdown()
        srv.server_close()


class TestTUIPhaseECommands(unittest.IsolatedAsyncioTestCase):

    async def test_tui_schedule_quiet_bg_and_untouched_agent(self):
        """Textual Pilot verifies /run --bg, /schedule, /quiet while leaving /agent and /agents untouched."""
        import tui.app as tui_app_mod
        from tui.app import ZaineTUI

        orig_agent = os.environ.get("ZAINE_AGENT")
        try:
            os.environ["ZAINE_AGENT"] = "1"
            created_calls: List[Dict[str, Any]] = []
            quiet_calls: List[Dict[str, Any]] = []
            agent_cmds: List[str] = []

            async def fake_status(base_url=None):
                return {"ok": True, "agent_enabled": True, "active_model": "zaine-reflex-7b", "mode": "jarvis"}

            async def fake_create_job(goal, *, schedule_kind="background", interval_seconds=0, daily_time="", run_at="", max_steps=8, base_url=None):
                created_calls.append({"goal": goal, "schedule_kind": schedule_kind, "interval_seconds": interval_seconds, "daily_time": daily_time})
                return {"ok": True, "job": {"job_id": "JOB-TUI01", "goal": goal, "schedule_kind": schedule_kind, "next_run_at": "2026-11-12T10:00:00+00:00"}}

            async def fake_get_sched(base_url=None):
                return {
                    "ok": True,
                    "quiet": {"enabled": True},
                    "jobs": [{"job_id": "JOB-TUI01", "schedule_kind": "interval", "status": "pending", "next_run_at": "2026-11-12T10:00:00Z", "goal": "Check logs"}],
                }

            async def fake_cancel(job_id, base_url=None):
                return {"ok": True, "job": {"job_id": job_id, "status": "cancelled"}}

            async def fake_quiet(enabled=None, *, reason="", clear_digest=False, base_url=None):
                quiet_calls.append({"enabled": enabled, "reason": reason})
                return {"ok": True, "quiet": {"enabled": True if enabled is None else bool(enabled), "reason": reason, "suppressed_count": 1, "digest": [{"ts": "now", "channel": "telegram_scheduler", "summary": "Muted"}]}}

            async def fake_agents(base_url=None):
                return {
                    "ok": True,
                    "agents": [
                        {
                            "agent_id": "zaine-jarvis",
                            "display_name": "J.A.R.V.I.S.",
                            "title": "Planner",
                            "tool_count": 3,
                            "interactive": True,
                            "auto_route": True,
                            "aliases": ["jarvis"],
                        }
                    ],
                    "pinned": None,
                    "last": None,
                }

            async def fake_set_agent(name, base_url=None):
                return {"ok": True, "pinned": None, "display_name": "Z.A.I.N.E", "message": f"Set agent: {name}"}

            orig_status = tui_app_mod.get_system_status
            orig_create = tui_app_mod.create_scheduled_job
            orig_sched = tui_app_mod.get_scheduler_status
            orig_cancel = tui_app_mod.cancel_scheduled_job
            orig_quiet = tui_app_mod.set_quiet_mode_remote
            orig_agents = tui_app_mod.get_agents
            orig_set_agent = tui_app_mod.set_agent
            tui_app_mod.get_system_status = fake_status
            tui_app_mod.create_scheduled_job = fake_create_job
            tui_app_mod.get_scheduler_status = fake_get_sched
            tui_app_mod.cancel_scheduled_job = fake_cancel
            tui_app_mod.set_quiet_mode_remote = fake_quiet
            tui_app_mod.get_agents = fake_agents
            tui_app_mod.set_agent = fake_set_agent

            app = ZaineTUI()
            orig_handle_agent = app.handle_agent_command

            def _track_agent(text):
                agent_cmds.append(text)
                return orig_handle_agent(text)

            app.handle_agent_command = _track_agent

            try:
                async with app.run_test(size=(150, 42)) as pilot:
                    app.system_facts["agent_enabled"] = True

                    # 1. /agent and /agents remain untouched
                    app._dispatch_user_turn("/agents")
                    app._dispatch_user_turn("/agent auto")
                    await pilot.pause(0.1)
                    self.assertEqual(agent_cmds, ["/agents", "/agent auto"])

                    # 2. /run --bg queues background goal
                    app._dispatch_user_turn("/run --bg Build workspace index")
                    await pilot.pause(0.1)
                    self.assertEqual(created_calls[-1]["schedule_kind"], "background")
                    self.assertEqual(created_calls[-1]["goal"], "Build workspace index")

                    # 3. /schedule interval, daily, list, cancel
                    app._dispatch_user_turn("/schedule every 30s Check logs")
                    await pilot.pause(0.1)
                    self.assertEqual(created_calls[-1]["schedule_kind"], "interval")
                    self.assertEqual(created_calls[-1]["interval_seconds"], 30)

                    app._dispatch_user_turn("/schedule daily 09:00 Morning audit")
                    await pilot.pause(0.1)
                    self.assertEqual(created_calls[-1]["schedule_kind"], "daily")
                    self.assertEqual(created_calls[-1]["daily_time"], "09:00")

                    app._dispatch_user_turn("/schedule list")
                    await pilot.pause(0.1)
                    app._dispatch_user_turn("/schedule cancel JOB-TUI01")
                    await pilot.pause(0.1)

                    # 4. /quiet on, digest, off
                    app._dispatch_user_turn("/quiet on Sleeping")
                    await pilot.pause(0.1)
                    app._dispatch_user_turn("/quiet digest")
                    await pilot.pause(0.1)
                    app._dispatch_user_turn("/quiet off")
                    await pilot.pause(0.1)

                    self.assertEqual(quiet_calls[0]["enabled"], True)
                    self.assertIsNone(quiet_calls[1]["enabled"])
                    self.assertEqual(quiet_calls[2]["enabled"], False)
                    cards = app.query(SystemCard)
                    self.assertTrue(any("BACKGROUND GOAL QUEUED" in c.title_text for c in cards))
                    self.assertTrue(any("GOAL SCHEDULED" in c.title_text for c in cards))
                    self.assertTrue(any("JOB CANCELLED" in c.title_text for c in cards))
                    msgs = app.query(AssistantTurnCard)
                    self.assertGreaterEqual(len(msgs), 3)
            finally:
                tui_app_mod.get_system_status = orig_status
                tui_app_mod.create_scheduled_job = orig_create
                tui_app_mod.get_scheduler_status = orig_sched
                tui_app_mod.cancel_scheduled_job = orig_cancel
                tui_app_mod.set_quiet_mode_remote = orig_quiet
                tui_app_mod.get_agents = orig_agents
                tui_app_mod.set_agent = orig_set_agent
        finally:
            if orig_agent is None:
                os.environ.pop("ZAINE_AGENT", None)
            else:
                os.environ["ZAINE_AGENT"] = orig_agent

