# Project-Z (Z.A.I.N.E) — Step 0 `STATE_REPORT.md`

Generated before any code edits or branch creation, per Step 0.

---

## 1. Environment, Repository & Baseline Findings (Critical Pre-Flight Facts)

| Item | Observed State |
| :--- | :--- |
| **IDE Active Workspace** | `e:\Autonomous Agent` (currently empty) |
| **Project-Z Git Repo Location** | `C:\Users\Mohemad Mateen ullah\Documents\projects\Project-Z` |
| **Current Branch / Commit** | `seminar-stable` @ `c37b8c0` (`main` and `remotes/origin/main` also present) |
| **Git Working Tree State** | **Dirty**: 97 entries (`61` modified/deleted tracked files including `agent.py`, `agents/profiles.json`, `agents/registry.py`, `core_router.py`, `core_service.py`, `requirements.txt`, `terminal_ui.py`; plus untracked `core/`, `db/`, `edith/`, `harness.py`, `tests/`) |
| **GPU / Idle VRAM (`nvidia-smi`)** | `NVIDIA GeForce RTX 2050`, `4096 MiB` total, `236 MiB` used, **`3727 MiB` free** |
| **Ollama (`0.40.15` client)** | Server not currently running (`could not connect`; `ollama list` timed out). On-disk manifests exist in `C:\Users\Mohemad Mateen ullah\.ollama\models\manifests` and `D:\ollama\models\manifests` for `zaine-reflex-7b:latest`, `qwen2.5:7b-instruct-q3_K_M`, `zaine-coder-7b:latest`, `qwen2.5-coder:7b-instruct-q3_K_M`, `qwen2.5:3b`, `moondream:latest`, `nomic-embed-text:latest` |
| **Python (`C:\Program Files\Python312\python.exe`)** | Missing several dependencies from `requirements.txt` and `tests/`: `requests`, `rich`, `textual`, `httpx`, `psutil` are not installed (25 packages present, including `pytest 8.2.0`, `pydantic 2.8.2`, `numpy 1.26.4`, `scipy 1.13.0`) |
| **Existing Test Suite (`tests/`)** | 18 `test_*.py` files containing **114** `def test_` / `async def test_` functions. Under current Python 3.12: **46 tests collect** across 12 files (`39 passed, 7 failed` due to offline Ollama and missing `textual`/`requests`), while **6 files fail collection** (`ModuleNotFoundError` for `textual`, `requests`, `httpx`, `rich`). *(Note: prompt states "106 tests" while disk currently has 114 test functions across `tests/` and deleted root `test_*.py` files in working tree.)* |
| **Mandatory Repo Rule (`AGENTS.md`)** | Any code modification to Project-Z requires appending a changelog entry to `PROJECT_HISTORY.md` |

---

## 2. What Exists Today (Module-by-Module Inventory)

### A. Core Service, Queueing, Approval & Model Routing
- **`core_service.py` (1,697 lines)**:
  - Runs `ZaineHTTPServer` (`ThreadingHTTPServer`) on `:7860`, writes `.zaine_core.json`, authenticates via `X-Zaine-Token` (`_validate_auth`), validates host/origin, and exposes `GET` (`/api/health`, `/api/queue`, `/api/requests/<id>`, `/api/status`, `/api/agents`, `/api/mode`, `/api/voice/status`, `/api/history`, `/api/lockscreen/status`, `/api/approval/pending`, `/api/jobs/stream`, `/api/hud/events`, `/api/jobs`, `/api/sessions`) and `POST` (`/api/mode`, `/api/agent`, `/api/voice/toggle`, `/api/context/clear`, `/api/approval/respond`, `/api/chat/cancel`, `/api/chat`, `/api/chat/stream`, `/api/jobs`, `/api/sessions`).
  - `/api/chat/stream` emits SSE events (`queued`, `warming`, `running`, `heartbeat`, `tool_event`, `token`, `done`, `error`) and checks `is_request_cancelled(request_id)` between yielded chunks (line 1420).
  - Prewarms the single model on startup in `_start_prewarm()`.
- **`coordinator.py`**:
  - `RequestCoordinator` & `ManagedRequest`: FIFO 1-at-a-time execution lock, atomic idempotency (`request_id`, TTL 300s, max 100 entries), `claim_request`, `complete_request`, `fail_request`, `cancel_request`, `is_request_cancelled`, `get_queue_telemetry`.
- **`approval.py` (475 lines)**:
  - `ApprovalRegistry` backed by SQLite `data/zaine_approvals.db` (`proposals` table, `ACT-<12hex>`).
  - Thread-local `_stream_context` (`set_approval_listener`, `set_current_request_id`, `set_current_tool_name`).
  - `require_approval()` emits SSE `approval_required`, sends Telegram inline `[Approve / Deny / Explain]` buttons (`act_approve:`, `act_deny:`, `act_explain:`), sends SSE `approval_wait` heartbeats every 5s, and blocks in `wait_for_decision(timeout_seconds=180)`. On timeout or unattended run with no responder, returns `(False, "Expired: ...")` — never auto-approves.
- **`core_router.py` (222 lines) & `Modelfile.reflex7b`**:
  - `Modelfile.reflex7b`: `FROM qwen2.5:7b-instruct-q3_K_M`, `PARAMETER num_ctx 4096`, `temperature 0.3`.
  - `TieredBrainRouter`: reads `ZAINE_FAST` (**default `"1"`**, which picks `zaine-fast-3b` unless set `"0"` to pick `zaine-reflex-7b`), `ZAINE_SINGLE_MODEL` (default `"1"`). `deep_model` honors `single_model`, `coder_model = "zaine-coder-7b"`, `VISION_MODEL = "moondream:latest"`.
  - **Gap in `agent.py:1600-1606`**: When `task_tier == "DEEP_CODE"`, `agent.py` unconditionally sets `target_model = router.coder_model` (`zaine-coder-7b`), bypassing `ZAINE_SINGLE_MODEL=1`.

### B. Agent Execution, Envelopes, Harness & Circuit Breakers
- **`agent.py` (1,939 lines)**:
  - `ZaineAgent` handles `ConversationMemory`, prompt building (`build_system_prompt`), streaming calls directly via `requests.post("http://localhost:11434/api/chat")`, tool parsing (`_try_parse_tool_calls`), tool execution (`_execute_tool`), and synchronous 1-level delegation (`_delegate` / `_run_subagent`, `MAX_DELEGATION_DEPTH = 1`, `SUBAGENT_MAX_HOPS = 3`).
  - **Existing Gaps vs Requirements**:
    1. **Permission Bypass on Auto-Routed Turns (`agent.py:1264-1276`)**: `agent_profile.allows(name)` is ONLY enforced when `is_explicit` (`_delegation_depth > 0`, `selection.source in ("mention", "pinned")`, or `selection is None`). Auto-routed turns bypass `agent_profile.allows(name)` completely.
    2. **Broken `is_tool_permitted` Lookup (`agent.py:1278`)**: Calls `is_tool_permitted(name, getattr(agent_profile, "name", None))` — `AgentProfile` defines `.agent_id`, not `.name`, so `None` is always passed.
    3. **No Malformed-JSON Retry/Repair Loop**: `_try_parse_tool_calls` attempts `raw_decode` -> `ast.literal_eval` -> regex -> `[TOOL]` recovery; if all fail, no repair/retry prompt is sent to the model (it just treats output as conversational text).
    4. **No Plan -> Act -> Observe -> Reflect Loop / Wall-Clock Timeout / Progress Detector**: While `CallTracker` (`harness.py`) detects 3 identical calls/errors, there is no step-level `plan`/`observe`/`reflect` SSE emission, no overall run wall-clock deadline enforcement inside the LLM/tool loop, and no general "no progress for N steps" detector.
    5. **Cancellation Lag**: Cancel is checked in `core_service.py` between yielded chunks, not inside Ollama's `resp.iter_lines()` socket read or `_run_subagent()`.
    6. **Subagent Return Shape**: `_run_subagent()` returns a plain string instead of structured `{status, summary, artifacts, errors}`.
    7. **Parallel Tool Execution (`agent.py:1845-1846`)**: Calls `router.execute_tools_parallel` if `len(tool_calls) > 1`, complicating deterministic single-step safety/approval ordering.
- **`agents/profiles.json` & `agents/registry.py` (already exists, differs from spec)**:
  - Existing profiles (`zaine-jarvis` allow-all, `zaine-edith`, `zaine-friday`, `zaine-vision` with `VAULT_MEMORY`+`WEB_SOCIAL`, `zaine-ultron` no-tools critic, `zaine-dume` inactive) already work with `/api/agents`, `/api/agent`, `@mention`, and HUD display.
  - **Mismatch with Spec Part B**: Spec requests `agent/profiles/*.json`, `agent/registry.py`, `delegate(agent_id, task, context)`, and reassigns Marvel `display_name`s to `planner` (`J.A.R.V.I.S.`, read-only memory only), `coder` (`E.D.I.T.H.`), `researcher` (`F.R.I.D.A.Y.`), `vision` (Moondream + doc analyst with untrusted-data rule), and `reviewer` (Ultron-persona critic, no write tools).
- **`core/task_envelope.py`**:
  - Already defines `TaskEnvelope` (with `max_steps`, `deadline_s`, `privacy_class="LOCAL_ONLY"`), `ResultEnvelope` (with `status`, `summary`, `artifacts`, `tool_log`, `taint={"untrusted_inputs": False, "private": True}`), `current_agent_var`, `current_envelope_var`, and `is_tool_permitted`.
- **`core/circuit_breaker.py`**:
  - `CircuitBreakerManager` keyed by `(tool, target)` with `CLOSED` -> `RECORDING` -> `OPEN` -> `HALF_OPEN` (trips on 3 failures in 60s, exponential backoff 30s -> 300s), deterministically writes `failure_events` and `'candidate'` rules in `db/learned_rules.py`.
- **`harness.py`**:
  - Provides `tool_outcome()`, `compact()`, `ResultStore`, and `CallTracker` (`stuck()` detects 3 identical calls or 3 identical errors).

### C. Tools, Workspace Sandbox, Web & Vision
- **`tools.py` & `tool_clusters.py` & `toolmaker.py` & `browser_agent.py` & `vision.py`**:
  - `TOOL_REGISTRY`, `TOOL_DESCRIPTIONS`, and `TOOL_CLUSTERS` (`SYSTEM`, `DEV_CODE`, `MEDIA_STUDIO`, `WEB_SOCIAL`, `VAULT_MEMORY`, `TACTICAL_OSINT`) already exist, alongside 100+ alias mappings in `agent.py` and `_validate_tool_registrations()`.
  - **`edith/ast_security_gate.py` & `edith/worktree_manager.py`**: Implement 4-zone path classification (`Zone 0` immutable kernel through `Zone 3` `workspace/`), NTFS ADS/`~` 8.3 path rejection, AST scanning (`eval`/`exec`/`os.system`), unified diff generation, SHA-256 TOCTOU lock, and rollback on `py_compile` failure.
  - **Critical Enforcement Gaps**:
    1. `write_workspace_file` and `edit_workspace_file` (`tools.py:446-556`) overwrite files inside `get_workspace_dir()` **without generating/showing a diff** and do NOT route through `edith/worktree_manager.py` or `edith/ast_security_gate.py`.
    2. `run_python_script` (`tools.py:500-540`) falls back to `PROJECT_ROOT` outside `workspace/` if the file isn't in `workspace/` and executes without `require_approval()`.
    3. `execute_command` (`tools.py:559-654`) runs `shell=True` without `require_approval()` unless matching pip/npm/pipe-to-shell regexes or `ZAINE_DEMO=1`.
    4. `install_python_package` (`toolmaker.py:51-76`) runs `pip install` directly **without `require_approval()`**.
    5. `browse_web`, `search_and_extract`, `download_web_file` (`browser_agent.py`) and `search_web` (`tools.py:315-355`) perform outbound HTTP requests **without approval** and return raw text with **no untrusted-data sanitization/framing** against prompt injection.
    6. `analyze_image_with_ollama` (`vision.py:110+`) invokes `moondream:latest` without explicit `keep_alive=0` and without marking OCR/description output as untrusted data.

### D. Memory, Trust & Persistence
- **`obsidian_adapter.py`, `memory_manager.py`, `memory_types.py`, `memory.py`**:
  - `ObsidianAdapter` reads/writes Markdown + YAML frontmatter atomically to `vault/`, with path-traversal protection (`_is_safe_vault_path`).
  - `MemoryManager` enforces `DEFAULT_MAX_CHARS = 2000`, regex-based prompt-injection blocking (`MemoryPolicy`), and trust ceilings (`UNTRUSTED` for web/external). `build_memory_context()` blends Obsidian vault + legacy SQLite within 2,000 chars.
  - `db/engine.py` provides WAL-mode SQLite (`zaine_tasks.db`) with a dedicated single-writer queue and `data/failure_blackbox.jsonl` fallback.
  - `db/learned_rules.py` already ensures `llm_proposed` rules stay at `status = 'candidate'` (review queue via `list_candidate_rules()` / `approve_candidate_rule()`).
  - **Gaps**:
    1. `MemoryEntry` (`memory_types.py`) and SQLite `memories`/`task_learnings` (`memory.py`) do **not** carry a `privacy_taint` field (`LOCAL_ONLY` default) nor enforce a session-wide cloud-routing block when private data enters the context.
    2. No per-run durable **scratchpad** file/store exists for mid-run crash recovery (`task`, `plan`, `progress`, `results`, `/runs`).

### E. Scheduler, TUI & Observability
- **`heartbeat.py` & `telegram_bridge.py`**:
  - `HeartbeatDaemon` (15s loop) runs reminders, battery, briefing, disk, ergonomics, desk presence, YouTube schedule, and proactive observation, with `is_night_mode()` (22:00-08:30) and Telegram delivery (`send_telegram_alert`, quiet hours on video pushes). No scheduled/background goal runner or global quiet-mode toggle exists yet.
- **`tui/app.py`, `tui/widgets/hud.py`, `tui/widgets/header.py`, `tui/widgets/footer.py`, `tui/client.py`, `tui/exec_graph.py`, `tui/telemetry.py`**:
  - `AgentStateHUD` already renders only real values or `"n/a"` (`agent_name`, `model_tier`, `active_model`, `last_ttft`, `last_throughput`, `eval_counts`, `exec_graph`, `recent_tools`, vault stats, CPU/RAM/VRAM).
  - **HUD & Command Gaps**: HUD currently lacks **step `n/max`**, **active tool in use**, and **queue count/position** from `RequestCoordinator` telemetry. TUI already binds `Esc`/`Ctrl+C` -> `cancel_active_stream()` and `/agents` -> `handle_agent_command()`, but lacks `/agent <goal>`, `/runs`, and `/stop`.
- **JSON Audit Log**:
  - `ollama_profiler.py` logs inference metrics in memory, and `db/learned_rules.py` logs `failure_events`, but there is no per-run structured JSON audit trail file capturing `(agent, tool, args summary, result, approval decisions, timestamps)`.

---

## 3. What Will Be Reused vs Added

| Subsystem | Reuse As-Is / Extend | What Will Be Added (behind `ZAINE_AGENT=1`, default OFF) |
| :--- | :--- | :--- |
| **Core Server & Auth** | `core_service.py`, `X-Zaine-Token`, `/api/chat/stream`, `/api/chat/cancel`, `.zaine_core.json`, `coordinator.py` FIFO + idempotency | Wire new agent loop SSE events (`plan`, `step`, `reflection`, `audit`, `scratchpad`), `GET /api/runs`, `POST /api/runs/<id>/resume`, instant mid-stream cancellation inside Ollama streaming & subagents, queue depth in `/api/status` |
| **Approvals** | `approval.py` (`ApprovalRegistry`, `require_approval`, SSE cards, Telegram buttons, 180s expiry -> never auto-approve) | Enforce `require_approval()` uniformly on ALL side-effect tools (shell commands, pip/npm, external file writes, outbound web fetch, message sends) with diff preview payload |
| **Model & Prompt** | `Modelfile.reflex7b`, `core/prompt_compiler.py`, `core_router.py`, `ollama_profiler.py` | Fix `DEEP_CODE` model switch so `ZAINE_SINGLE_MODEL=1` strictly locks `zaine-reflex-7b`; enforce `keep_alive=0` on `moondream` (if ever invoked) + single-flight VRAM lock |
| **Subagents & Security** | `core/task_envelope.py` (`TaskEnvelope`, `ResultEnvelope`, `is_tool_permitted`), `harness.py`, `core/circuit_breaker.py`, `TOOL_REGISTRY`, `TOOL_CLUSTERS` | `agent/loop.py` (Plan->Act->Observe->Reflect, max steps, wall-clock deadline, 3-failure & N-no-progress circuit breaker, 1-repair + 1-retry JSON validator), `agent/registry.py`, `agent/profiles/*.json` (5 scoped profiles), `delegate(agent_id, task, context)` with depth=1, fix `.agent_id` & unconditional alias+allowed-tools check at execution time |
| **Workspace Sandbox** | `edith/ast_security_gate.py`, `edith/worktree_manager.py`, `tools.py` workspace helpers | Strict sandbox enforcement on read/write/run tools: block path traversal, read-only outside workspace unless approved, compute unified diff & show before overwrite, untrusted-data framing wrappers on vision & web outputs |
| **Memory & Resume** | `obsidian_adapter.py`, `memory_manager.py` (2000-char budget), `memory_types.py`, `db/engine.py`, `db/learned_rules.py` review queue | Add `privacy_taint` (`LOCAL_ONLY` default) to `MemoryEntry` & session taint tracker blocking any cloud routing; per-run crash-resumable scratchpad files (`data/runs/<run_id>.json`); candidate-fact review queue without autonomous promotion |
| **TUI & Audit** | `tui/app.py`, `tui/widgets/hud.py`, `tui/client.py`, `tui/exec_graph.py` | Add real `step n/max`, `tool in use`, `queue` to `AgentStateHUD` (`"n/a"` when inactive); add `/agent <goal>`, `/agents`, `/runs`, `/stop`; write per-run JSON audit log (`data/audit/<run_id>.json`) |
| **Scheduler (Phase 3 / E)** | `heartbeat.py` (`HeartbeatDaemon`), `telegram_bridge.py` | Add scheduled/background goal runner under `HeartbeatDaemon` + global quiet mode + Obsidian/Telegram result delivery + pause-for-approval on risky actions |

---

## 4. Risks for the 4GB VRAM GPU (RTX 2050 — 3,727 MiB Free at Idle)

1. **7B Q3_K_M RAM Spillover (~4.7GB model + KV cache on 4GB VRAM)**:
   - `zaine-reflex-7b` (`qwen2.5:7b-instruct-q3_K_M`) exceeds 3.7GB free VRAM once KV cache is allocated, causing PCIe layer offloading and ~8 tok/s generation speed.
   - **Mitigation**: Keep `num_ctx <= 4096` (launchers currently set `ZAINE_NUM_CTX=6144` in `zaine.bat`/`run_demo_fast.bat`, which expands KV cache VRAM!). Keep subagent prompts scoped (`<= 2000` chars memory + compact tool schemas per profile) so prompt eval doesn't stall on CPU-offloaded layers.
2. **Accidental Model Swap / Eviction Thrash**:
   - `agent.py:1600` currently switches to `zaine-coder-7b` on `DEEP_CODE`, and `core_router.py` defaults `ZAINE_FAST="1"` (`zaine-fast-3b`). Loading a second 3B/7B model forces Ollama to unload `zaine-reflex-7b`, causing reload stalls or OOM.
   - **Mitigation**: When `ZAINE_AGENT=1` + `ZAINE_SINGLE_MODEL=1`, lock all text turns (planner, coder, researcher, reviewer, orchestrator) strictly to `zaine-reflex-7b` and serialize inference through `coordinator.py`.
3. **Moondream Vision Model Co-Residency Collision**:
   - `vision.py` invokes `moondream:latest` without `keep_alive=0`. Co-loading Moondream while `zaine-reflex-7b` is resident risks evicting the 7B model from the `3,727 MiB` free VRAM or causing allocation failures.
   - **Mitigation**: Gate Vision calls cleanly via sequential execution, use `keep_alive: 0` on `moondream:latest` so it releases VRAM immediately after image analysis, and monitor peak VRAM via `nvidia-smi` / `tui/telemetry.py`. Because `zaine-reflex-7b` (`qwen2.5:7b-instruct-q3_K_M`) + KV cache already exceeds `3,727 MiB` free VRAM and relies on Ollama layer offloading, keeping peak VRAM `< 3.5GB` will require benchmarking Ollama's actual `num_gpu` / `num_ctx` split as soon as Ollama is started.
4. **Background / Parallel Calls Starving VRAM**:
   - `agent.py:1845` runs `execute_tools_parallel`, and `reflect_on_task_async` fires Ollama `/api/generate` in the background. If two LLM calls overlap (e.g., reflection or scheduler hitting Ollama during an active turn), Ollama serializes or evicts contexts.
   - **Mitigation**: Keep `ZAINE_REFLECT=0` during agent runs, disable parallel LLM subagent execution (`coordinator.py` sequential lock), and yield between subagent hops only after tool completion.

---

## 5. Open Questions / Clarifications Needed Before Step 2 (Phase A)

Before I create branch `agent-core` or write any code, please confirm:

1. **Workspace & Target Repo Path**:
   - The IDE workspace open right now is `e:\Autonomous Agent` (empty), whereas the Project-Z codebase is at `C:\Users\Mohemad Mateen ullah\Documents\projects\Project-Z`. Should I work directly inside `C:\Users\Mohemad Mateen ullah\Documents\projects\Project-Z` (please add/open it as a workspace folder if needed)?
2. **Git Branch Base (`agent-core`)**:
   - `C:\Users\Mohemad Mateen ullah\Documents\projects\Project-Z` currently has a dirty `seminar-stable` branch (`61` modified/deleted tracked files + `core/`, `db/`, `edith/`, `tests/`, `harness.py` untracked). Should I:
     - **(a)** Commit or stash the current `seminar-stable` changes first and branch `agent-core` off that clean commit, OR
     - **(b)** Branch `agent-core` directly from the current working tree (carrying those uncommitted `core/`, `edith/`, `db/`, `tests/` files cleanly onto `agent-core`), leaving `seminar-stable` untouched, OR
     - **(c)** Branch `agent-core` from `HEAD` (`c37b8c0`) cleanly?
3. **Existing `agents/` vs Requested `agent/` Module & Role Mapping**:
   - `Project-Z` already has `agents/registry.py` and `agents/profiles.json` where **J.A.R.V.I.S.** is the tool-rich orchestrator, **Vision** handles memory/web, and **F.R.I.D.A.Y.** handles OSINT/system. Your spec asks for `agent/loop.py`, `agent/profiles/*.json`, `agent/registry.py` with **planner (`J.A.R.V.I.S.`)**, **coder (`E.D.I.T.H.`)**, **researcher (`F.R.I.D.A.Y.`)**, **vision/doc (`Vision`)**, and **reviewer (`Ultron`)**.
   - Keeping legacy `agents/` untouched when `ZAINE_AGENT=0` (default OFF) preserves existing tests/behavior, while `agent/` runs when `ZAINE_AGENT=1`. Confirm if you want `agent/` built cleanly alongside legacy `agents/` (preserving `ZAINE_AGENT=0` behavior 100%) vs replacing `agents/` directly.
4. **`/agent` Slash Command Disambiguation**:
   - `tui/app.py` already uses `/agent` (list agents), `/agent <name>` (pin agent), `/agent auto`, and `@<name>`. Since you asked for `/agent <goal>`, `/agents`, `/runs`, `/stop`: when `ZAINE_AGENT=1`, should `/agents` list agents, `/agent pin <name|auto>` (or known profile names) pin, and `/agent <anything else>` start an autonomous goal run — or should `/agent <goal>` always launch a goal run?
5. **Missing Python Dependencies & Ollama Daemon**:
   - `C:\Program Files\Python312\python.exe` lacks `requests`, `rich`, `textual`, `httpx`, `psutil` (preventing 6 of 18 test files and `agent.py`/`core_service.py` from importing), and `ollama` daemon is offline (`Unable to init instance`). Should I install `requirements.txt` (plus `httpx` if needed) into Python 3.12 or a local `.venv` before Phase A testing, and check why `ollama serve` failed to init?
6. **Peak VRAM `< 3.5GB` Constraint Check**:
   - With `236 MiB` idle desktop VRAM out of `4096 MiB` (`3,727 MiB` free), loading `zaine-reflex-7b` (`qwen2.5:7b-instruct-q3_K_M`, ~4.7GB total model + KV cache) relies on Ollama layer offloading and `num_ctx`. Once Ollama is online, do you want me to benchmark VRAM first and adjust `num_ctx` (e.g., `4096` vs smaller) or `num_gpu` if needed to keep peak `< 3.5GB`?

---

*Stopped at Step 1 — awaiting your OK and answers to the questions above before creating `agent-core` or starting Phase A.*
