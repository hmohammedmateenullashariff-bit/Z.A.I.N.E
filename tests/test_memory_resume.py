"""
Phase D tests:
1. Default LOCAL_ONLY privacy taint on vault MemoryEntry (YAML roundtrip) & legacy SQLite migration.
2. Cloud routing block (PrivacyViolationError) on model endpoints and outbound tools when LOCAL_ONLY data is active, while keeping localhost/loopback permitted.
3. No autonomous trust promotion (Constraint #5): repeated assertions route strictly to `memory_review_queue` until explicit operator approval.
4. Step-relevant retrieval within ~2000-char budget via `retrieve_step_memory` & dynamic step replacement in `AutonomousLoop`.
5. Crash/kill scratchpad persistence and recovery via `RunScratchpadStore.list_runs(resumable_only=True)` + `AutonomousLoop.resume()`.
6. ZAINE_AGENT=0 parity preservation for legacy `memory.save_memory` / `memory.get_memory`.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import db.engine as db_engine
import memory
import memory_manager as mm_mod
from autonomy.guards import require_side_effect_approval
from autonomy.loop import AutonomousLoop, LoopConfig
from autonomy.memory_bridge import MAX_MEMORY_BUDGET_CHARS, retrieve_step_memory
from autonomy.memory_review import (
    approve_review_item,
    list_review_queue,
    record_agent_fact,
    reject_review_item,
    submit_fact_candidate,
)
from autonomy.privacy import (
    PrivacyViolationError,
    assert_local_routing,
    check_outbound_cloud_block,
    is_session_private,
    mark_session_private,
    scoped_privacy_session,
)
from autonomy.scratchpad import RunScratchpad, RunScratchpadStore
from core.circuit_breaker import CircuitBreakerManager
from core.task_envelope import TaskEnvelope
from memory_types import MemoryEntry, MemorySource, MemoryType, PrivacyTaint, TrustLevel
from obsidian_adapter import ObsidianAdapter


def _fake_stream_from_text(text: str, *, eval_tokens: int = 12) -> Iterator[Dict[str, Any]]:
    yield {"message": {"content": text}, "done": False}
    yield {
        "done": True,
        "load_duration": 0,
        "prompt_eval_count": 40,
        "prompt_eval_duration": 1000,
        "eval_count": eval_tokens,
        "eval_duration": 1000,
    }


@pytest.fixture()
def isolated_memory_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vault_dir = tmp_path / "dev_vault"
    vault_dir.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "zaine_test.db"
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    test_eng = db_engine.DatabaseEngine(db_path=db_file)
    monkeypatch.setenv("ZAINE_OBSIDIAN_VAULT_PATH", str(vault_dir))
    monkeypatch.setenv("ZAINE_RUNS_DIR", str(runs_dir))
    monkeypatch.setenv("ZAINE_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setattr(memory, "DB_PATH", db_file)
    monkeypatch.setattr(db_engine, "get_db_engine", lambda: test_eng)
    mm_mod._manager_instance = None

    yield {
        "vault_dir": vault_dir,
        "db_file": db_file,
        "runs_dir": runs_dir,
        "engine": test_eng,
    }

    mm_mod._manager_instance = None


def test_privacy_taint_defaults_and_sqlite_migration(isolated_memory_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ZAINE_AGENT", "0")
    db_file = isolated_memory_env["db_file"]

    # Create pre-Phase-D legacy tables WITHOUT privacy_taint and verify non-destructive migration
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE memories (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)")
    conn.execute(
        "INSERT INTO memories (key, value, updated_at) VALUES (?, ?, ?)",
        ("legacy_fact", "preexisting row", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    with_taint = memory.get_all_memories_with_taint()
    assert with_taint["legacy_fact"]["value"] == "preexisting row"
    assert with_taint["legacy_fact"]["privacy_taint"] == "LOCAL_ONLY"

    # MemoryEntry YAML roundtrip defaults to LOCAL_ONLY even when frontmatter omits privacy_taint
    mm = mm_mod.get_memory_manager()
    entry, msg = mm.create(
        title="Postgres Credentials Note",
        content="Use local socket postgres port 5432 in dev.",
        mem_type=MemoryType.FACT,
        source=MemorySource.USER,
    )
    assert entry is not None, msg
    assert entry.privacy_taint == PrivacyTaint.LOCAL_ONLY.value

    md = entry.to_markdown()
    assert "privacy_taint: LOCAL_ONLY" in md
    parsed = ObsidianAdapter.parse_markdown(md)
    assert parsed is not None
    assert parsed.privacy_taint == "LOCAL_ONLY"

    legacy_md = md.replace("privacy_taint: LOCAL_ONLY\n", "")
    parsed_legacy = ObsidianAdapter.parse_markdown(legacy_md)
    assert parsed_legacy is not None
    assert parsed_legacy.privacy_taint == "LOCAL_ONLY"

    on_disk = mm.adapter.read(entry.id)
    assert on_disk is not None and on_disk.privacy_taint == "LOCAL_ONLY"


def test_cloud_routing_blocked_when_local_only_session_active(isolated_memory_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ZAINE_AGENT", "1")
    monkeypatch.setenv("ZAINE_OLLAMA_URL", "https://api.openai.com/v1/chat/completions")

    with scoped_privacy_session("LOCAL_ONLY"):
        mark_session_private("vault:MEM-001", "LOCAL_ONLY")
        assert is_session_private() is True

        # Localhost stays permitted even with LOCAL_ONLY private data in session
        assert_local_routing("http://127.0.0.1:11434/api/chat", context="test_local")
        assert_local_routing("http://localhost:11434/api/chat", context="test_localhost")

        # Cloud endpoint in tool check is blocked before approval
        reason = check_outbound_cloud_block(
            "query_public_api",
            {"url": "https://api.openai.com/v1/chat/completions"},
        )
        assert reason is not None
        assert "LOCAL_ONLY" in reason

        ok_ap, msg_ap = require_side_effect_approval(
            "query_public_api",
            {"url": "https://api.anthropic.com/v1/messages"},
        )
        assert ok_ap is False
        assert "Privacy boundary blocked" in msg_ap

    # AutonomousLoop blocks non-local model routing with PrivacyViolationError
    def fake_model(payload, cancel_token, timeout_s):
        yield from _fake_stream_from_text('{"plan": ["Step 1"], "direct": true}')

    loop = AutonomousLoop(
        config=LoopConfig(max_steps=2, wall_clock_timeout_s=15.0),
        model_stream_fn=fake_model,
        breaker=CircuitBreakerManager(isolated_memory_env["engine"]),
        memory_context="[LOCAL_ONLY] secret local note",
        scratchpad_store=RunScratchpadStore(isolated_memory_env["runs_dir"]),
    )
    with pytest.raises(PrivacyViolationError):
        loop.run(
            "Summarize my private local note",
            envelope=TaskEnvelope(goal="Summarize", privacy_class="LOCAL_ONLY", max_steps=2),
        )


def test_no_autonomous_trust_promotion_queues_repeated_facts(isolated_memory_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ZAINE_AGENT", "1")
    eng = isolated_memory_env["engine"]
    mm = mm_mod.get_memory_manager()

    # 1. Record inferred fact first time -> stored strictly as provisional (never promoted)
    r1 = record_agent_fact(
        "SQLite WAL Rule",
        "Always route writes through DatabaseEngine single-writer queue.",
        source=MemorySource.AGENT_INFERENCE,
        memory_manager=mm,
        engine=eng,
    )
    assert r1["status"] == "stored_provisional"
    assert r1["trust"] == TrustLevel.PROVISIONAL.value
    assert r1["trust_promoted"] is False
    mem_id = r1["memory_id"]

    # Direct autonomous update attempt to VERIFIED without user_approved=True is blocked
    upd_entry, upd_msg = mm.update(mem_id, trust=TrustLevel.VERIFIED, user_approved=False)
    assert upd_entry is None
    assert "Autonomous trust promotion blocked" in upd_msg

    # 2. Repeated assertion goes strictly to review queue with incrementing repeat_count
    r2 = record_agent_fact(
        "SQLite WAL Rule",
        "Always route writes through DatabaseEngine single-writer queue.",
        source=MemorySource.AGENT_INFERENCE,
        memory_manager=mm,
        engine=eng,
    )
    r3 = record_agent_fact(
        "SQLite WAL Rule",
        "Always route writes through DatabaseEngine single-writer queue.",
        source=MemorySource.AGENT_INFERENCE,
        memory_manager=mm,
        engine=eng,
    )
    assert r2["queued_for_review"] is True and r2["trust_promoted"] is False
    assert r3["queued_for_review"] is True and r3["trust_promoted"] is False
    assert r3["repeat_count"] == 2

    still_prov = mm.adapter.read(mem_id)
    assert still_prov is not None
    assert still_prov.trust == TrustLevel.PROVISIONAL

    # 3. Repeated SQLite save_memory under ZAINE_AGENT=1 also refuses silent overwrite/promotion
    s1 = memory.save_memory("deploy_target", "local-rtx2050", source=MemorySource.AGENT_INFERENCE)
    assert "Remembered:" in s1
    s2 = memory.save_memory("deploy_target", "local-rtx2050", source=MemorySource.AGENT_INFERENCE)
    assert "Queued repeated/inferred fact" in s2 and "trust not promoted" in s2

    pending = list_review_queue(status="pending_review", engine=eng)
    assert len(pending) >= 2
    wal_item = next(item for item in pending if item["title"] == "SQLite WAL Rule")
    assert wal_item["repeat_count"] == 2
    assert wal_item["proposed_trust"] == TrustLevel.PROVISIONAL.value

    # 4. Explicit operator approval CAN promote
    ok_app, app_msg = approve_review_item(
        wal_item["id"],
        promote_to=TrustLevel.VERIFIED,
        memory_manager=mm,
        engine=eng,
    )
    assert ok_app is True, app_msg
    promoted = mm.adapter.read(mem_id)
    assert promoted is not None
    assert promoted.trust == TrustLevel.VERIFIED

    # Rejection marks status rejected cleanly
    deploy_item = next(item for item in pending if item["title"] == "deploy_target")
    ok_rej, _ = reject_review_item(deploy_item["id"], engine=eng)
    assert ok_rej is True


def test_step_relevant_retrieval_budget_and_step_switching(isolated_memory_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ZAINE_AGENT", "1")
    monkeypatch.setenv("ZAINE_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
    mm = mm_mod.get_memory_manager()

    # Seed distinct domain notes + an oversized note to verify relevance filtering & <= 2000 budget
    mm.create(
        title="Postgres Migration Policy",
        content="Use alembic revision --autogenerate for postgres migrations and check indexes. " + ("X" * 900),
        tags=["postgres", "migration"],
        source=MemorySource.USER,
    )
    mm.create(
        title="Docker Compose Setup",
        content="Run docker compose build with buildkit cache disabled for container tests.",
        tags=["docker", "compose"],
        source=MemorySource.USER,
    )
    mm.create(
        title="Gardening Schedule",
        content="Water the balcony mint plants every Tuesday and Friday morning.",
        tags=["gardening", "plants"],
        source=MemorySource.USER,
    )

    pg_ctx, pg_meta = retrieve_step_memory(
        "Prepare backend deployment",
        current_step="Check postgres migration script before release",
        max_chars=MAX_MEMORY_BUDGET_CHARS,
    )
    assert "Postgres Migration Policy" in pg_ctx
    assert "Docker Compose Setup" not in pg_ctx
    assert "Gardening Schedule" not in pg_ctx
    assert len(pg_ctx) <= MAX_MEMORY_BUDGET_CHARS
    assert pg_meta["taint"] == "LOCAL_ONLY"

    seen_system_prompts: List[str] = []

    def fake_model(payload, cancel_token, timeout_s):
        msgs = payload.get("messages") or []
        sys_text = str(msgs[0].get("content", "")) if msgs else ""
        if "task planner" in sys_text:
            yield from _fake_stream_from_text(
                json.dumps(
                    {
                        "plan": [
                            "Check postgres migration script",
                            "Verify docker compose build",
                        ],
                        "direct": False,
                    }
                )
            )
            return

        seen_system_prompts.append(sys_text)
        call_idx = len(seen_system_prompts)
        if call_idx == 1:
            yield from _fake_stream_from_text('{"tool": "noop_step", "args": {"phase": "pg"}}')
        else:
            yield from _fake_stream_from_text("Both postgres and docker checks completed cleanly.")

    events: List[tuple] = []
    loop = AutonomousLoop(
        config=LoopConfig(max_steps=4, wall_clock_timeout_s=20.0, max_memory_chars=2000),
        model_stream_fn=fake_model,
        tool_exec_fn=lambda tc: "ok: verified",
        breaker=CircuitBreakerManager(isolated_memory_env["engine"]),
        scratchpad_store=RunScratchpadStore(isolated_memory_env["runs_dir"]),
        on_event=lambda st, t, d: events.append((st, t, d)),
    )
    res = loop.run("Check postgres migration and docker compose setup")
    assert res.status == "completed"
    assert len(seen_system_prompts) == 2

    # Step 1 got postgres note ONLY; Step 2 evicted postgres note and got docker note ONLY
    assert "Postgres Migration Policy" in seen_system_prompts[0]
    assert "Docker Compose Setup" not in seen_system_prompts[0]
    assert "Gardening Schedule" not in seen_system_prompts[0]

    assert "Docker Compose Setup" in seen_system_prompts[1]
    assert "Postgres Migration Policy" not in seen_system_prompts[1]
    assert "Gardening Schedule" not in seen_system_prompts[1]

    mem_events = [d for st, _t, d in events if st == "memory"]
    assert len(mem_events) == 2
    assert all(ev["chars"] <= MAX_MEMORY_BUDGET_CHARS for ev in mem_events)


def test_crash_and_restart_resume_from_scratchpad(isolated_memory_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ZAINE_AGENT", "1")
    monkeypatch.setenv("ZAINE_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
    runs_dir = isolated_memory_env["runs_dir"]
    db_file = isolated_memory_env["db_file"]
    vault_dir = isolated_memory_env["vault_dir"]

    # Spawn an isolated worker subprocess running step 1 then crashing mid-step-2 via SIGTERM/kill
    crash_marker = runs_dir / "step1_ready.flag"
    worker_code = f"""
import json, os, time, sys
from pathlib import Path
sys.path.insert(0, {str(PROJECT_ROOT)!r})
import db.engine as db_engine
from autonomy.loop import AutonomousLoop, LoopConfig
from autonomy.scratchpad import RunScratchpadStore
from core.circuit_breaker import CircuitBreakerManager

eng = db_engine.DatabaseEngine(db_path=Path({str(db_file)!r}))
calls = 0
def model_fn(payload, cancel_token, timeout_s):
    global calls
    msgs = payload.get("messages") or []
    if "task planner" in str(msgs[0].get("content", "")):
        yield {{"message": {{"content": json.dumps({{"plan": ["Run step one tool", "Run step two and finish"], "direct": False}})}}, "done": False}}
        yield {{"done": True, "prompt_eval_count": 20, "eval_count": 10}}
        return
    calls += 1
    if calls == 1:
        yield {{"message": {{"content": '{{"tool": "write_step1", "args": {{"item": "alpha"}}}}'}}, "done": False}}
        yield {{"done": True, "prompt_eval_count": 20, "eval_count": 10}}
        return
    Path({str(crash_marker)!r}).write_text("ready", encoding="utf-8")
    time.sleep(30)

loop = AutonomousLoop(
    config=LoopConfig(max_steps=4, wall_clock_timeout_s=60.0),
    model_stream_fn=model_fn,
    tool_exec_fn=lambda tc: "step1 output alpha",
    breaker=CircuitBreakerManager(eng),
    scratchpad_store=RunScratchpadStore(Path({str(runs_dir)!r})),
)
loop.run("Two-step resumable task", run_id="RUN-CRASH-TEST")
"""
    env = os.environ.copy()
    env["ZAINE_AGENT"] = "1"
    env["ZAINE_RUNS_DIR"] = str(runs_dir)
    env["ZAINE_OBSIDIAN_VAULT_PATH"] = str(vault_dir)
    env["ZAINE_OLLAMA_URL"] = "http://127.0.0.1:11434/api/chat"

    proc = subprocess.Popen([sys.executable, "-c", worker_code], env=env, cwd=str(PROJECT_ROOT))
    t0 = time.monotonic()
    while not crash_marker.exists():
        if time.monotonic() - t0 > 15.0:
            proc.kill()
            pytest.fail("Worker subprocess did not reach step 2 crash marker in time.")
        time.sleep(0.05)

    # Hard-kill process mid-step-2 (process crash simulation)
    proc.kill()
    proc.wait(timeout=5)

    # Restart phase: fresh RunScratchpadStore sees the interrupted run as resumable
    store2 = RunScratchpadStore(runs_dir)
    listed = store2.list_runs(resumable_only=True)
    assert any(r["run_id"] == "RUN-CRASH-TEST" and r["resumable"] is True for r in listed)
    match = next(r for r in listed if r["run_id"] == "RUN-CRASH-TEST")
    assert match["effective_status"] == "interrupted (resumable)"
    assert match["completed_steps"] == 1
    assert match["current_step"] == 2

    # Resume in a brand new AutonomousLoop; plan() and step 1 must NOT re-run
    resumed_calls: List[str] = []

    def resume_model_fn(payload, cancel_token, timeout_s):
        msgs = payload.get("messages") or []
        sys_txt = str(msgs[0].get("content", ""))
        assert "task planner" not in sys_txt, "Resume should reuse saved plan instead of re-planning"
        joined = "\n".join(str(m.get("content", "")) for m in msgs)
        resumed_calls.append(joined)
        if len(resumed_calls) == 1:
            assert "step1 output alpha" in joined
            yield from _fake_stream_from_text('{"tool": "finish_step2", "args": {"item": "beta"}}')
        else:
            yield from _fake_stream_from_text("Resumed and completed step 2 cleanly.")

    resumed_events: List[tuple] = []
    loop2 = AutonomousLoop(
        config=LoopConfig(max_steps=4, wall_clock_timeout_s=20.0),
        model_stream_fn=resume_model_fn,
        tool_exec_fn=lambda tc: "step2 output beta",
        breaker=CircuitBreakerManager(isolated_memory_env["engine"]),
        scratchpad_store=store2,
        on_event=lambda st, t, d: resumed_events.append((st, t, d)),
    )
    res2 = loop2.resume("RUN-CRASH-TEST")
    assert res2.status == "completed"
    assert res2.run_id == "RUN-CRASH-TEST"
    assert "Resumed and completed step 2 cleanly." in res2.summary
    assert any(st == "resume" for st, _t, _d in resumed_events)

    # Completed run drops out of resumable_only=True list
    pad_after = store2.load("RUN-CRASH-TEST")
    assert pad_after is not None and pad_after.status == "completed" and pad_after.resumable is False
    assert not any(r["run_id"] == "RUN-CRASH-TEST" for r in store2.list_runs(resumable_only=True))


def test_zaine_agent_zero_legacy_memory_parity(isolated_memory_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ZAINE_AGENT", "0")
    out1 = memory.save_memory("favorite_editor", "neovim")
    assert "Remembered: 'favorite_editor' = 'neovim'" in out1
    # Overwrite behaves identically to baseline when ZAINE_AGENT=0
    out2 = memory.save_memory("favorite_editor", "vscode")
    assert "Remembered: 'favorite_editor' = 'vscode'" in out2
    assert "vscode" in memory.get_memory("favorite_editor")
