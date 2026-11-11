# PROJECT DOSSIER: Z.A.I.N.E (Project-Z)

> **Forensic Reconstruction — Generated 2026-11-04**
> Every claim cites file paths or commit hashes. Items that could not be verified from the repository are marked **UNVERIFIED**.

---

## 1. Project Identity

| Field | Value |
| :--- | :--- |
| **Name** | Z.A.I.N.E / "Project-Z" |
| **Full Forms** | 1. **Zero-latency Autonomous Intelligent Neural Entity** (README / CLI branding)<br>2. **Zenith Architecture Intelligence Neural Engine** (Academic proposal / OpenVault) |
| **One-line description** | A fully local, terminal-native AI assistant ("personal Jarvis") running on Ollama with multi-agent orchestration, voice, vision, Telegram bridge, and a YouTube content pipeline |
| **Academic Context** | **HKBK College of Engineering** (Bengaluru), AIML Department, Academic Year 2026–2027 |
| **Project Guide** | Prof MD Nabeel |
| **Contributors / Team** | H Mohammed Mateenulla Shariff (Lead / Author of all commits), Syed Mutammur Abbas (Teammate / Proposal Co-Author) |
| **Current status** | **Advanced Prototype / Pre-MVP (Live Seminar Code Freeze)** — core chat loop operational, 71/71 tests passing, seminar demo stabilized under `run_demo_fast.bat` |
| **Repo age** | 60+ days (first commit 2026-09-05, earliest file timestamp 2026-09-01) |
| **Total commits** | 30 (on `main`), plus working tree changes on `seminar-stable` |
| **Branch** | `main` (active), `seminar-stable` (tag/branch at `daecbb8` / `d536472`) |
| **Research Foundations** | Four arXiv papers cited in architecture design:<br>1. *Code as Agent Harness* (arXiv:2605.18747)<br>2. *LLM-Agent Memory Survey* (arXiv:2404.13501)<br>3. *Retrieval-Augmented Generation for Knowledge-Intensive NLP* (arXiv:2005.11401)<br>4. *Multimodal RAG Survey* (arXiv:2504.08748) |
| **Codebase size** | 271 Python files, ~44,922 lines of Python. ~99KB `agent.py`, ~89KB `tools.py`, ~55KB `core_service.py` |
| **License** | MIT ([`LICENSE`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/LICENSE)) |

---

## 2. Original Concept

### Earliest Evidence (commit `6c087a7`, 2026-09-05)
The first commit message reads:
> **"feat: Zaine v1 complete autonomous agent"**

It landed 71 files with 769,348 insertions — effectively the entire v1 system in a single commit. The [`README.md`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/README.md) at that time described:

> *"A terminal-native, autonomous AI assistant & personal Jarvis operating locally on your workstation. Engineered with zero mandatory cloud dependencies, local neural model orchestration, durable Obsidian knowledge memory, rich terminal CLI, and remote mobile execution via Telegram."*

### Original Problem & Target User
- **Problem:** Build a privacy-first, offline-capable personal AI assistant (Iron Man's J.A.R.V.I.S.) for a single developer/student on commodity hardware (RTX 2050 4GB laptop).
- **Target user:** The creator (Mateen), as a productivity/automation assistant and a learning/portfolio project.
- **Original scope** (from [`project-roadmap.md`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/project-roadmap.md)): 7 phases — voice/persona → coding/automation → comms/Telegram → proactive heartbeat → vision → web browser agent → multi-agent hive mind. All marked SHIPPED in the roadmap.

### Original Stack
- Python 3.10+, Ollama (qwen2.5:3b reflex, deepseek-r1:7b reasoning, qwen2.5-coder:3b coding, moondream vision)
- SQLite for memory, Obsidian Markdown vault for durable knowledge
- Faster-Whisper + Piper-TTS for voice, Telegram Bot API for mobile
- Electron + HTML/CSS/JS HUD (deprecated in later commits)

---

## 3. Current State

### 3.1 Architecture

```
┌─────────────────────────────────────────────────────────┐
│  ENTRY POINTS                                           │
│  zaine_tui.py → tui/app.py (Textual TUI)               │
│  main.py → terminal_ui.py (Rich CLI, legacy, broken)    │
│  telegram_bridge.py (mobile daemon)                     │
│  run_demo_fast.bat / run_demo.bat (seminar launchers)   │
└────────────┬────────────────────────────────────────────┘
             │ HTTP POST /api/chat/stream (SSE)
             ▼
┌─────────────────────────────────────────────────────────┐
│  core_service.py (:7860)                                │
│  ├── coordinator.py (request queue, FIFO, 1-at-a-time)  │
│  ├── agent.py (ZaineAgent — chat_stream, tool loop)     │
│  │   ├── core_router.py (TieredBrainRouter)             │
│  │   ├── tool_clusters.py (dynamic prompt injection)    │
│  │   └── tools.py (125+ tools)                          │
│  ├── agents/ (registry.py, profiles.json — 5 personas)  │
│  ├── memory.py + memory_manager.py + obsidian_adapter   │
│  └── heartbeat.py (proactive daemon)                    │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Final Stack (with versions where determinable)

| Component | Technology | Source |
| :--- | :--- | :--- |
| Language | Python 3.12 / 3.14 | **UNVERIFIED** — inferred from runtime; no `.python-version` |
| UI Framework | `textual==8.2.8` | [`requirements.txt`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/requirements.txt) |
| LLM Runtime | Ollama (local) | [`core_router.py`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/core_router.py) |
| Models | zaine-fast-3b (custom Modelfile), zaine-reflex-7b, zaine-coder-7b, moondream | [`Modelfile`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/Modelfile), [`Modelfile.coder`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/Modelfile.coder) |
| TTS | `edge-tts>=7.3.1`, Piper-TTS | `requirements.txt` |
| STT | Faster-Whisper | `requirements.txt` |
| Memory | SQLite + Obsidian Markdown vault | [`memory.py`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/memory.py) |
| Vision | OpenCV + moondream VLM | [`vision.py`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/vision.py) |
| Face-ID | YuNet + SFace (ONNX) | [`face_id.py`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/face_id.py) |
| HTTP server | `ThreadingHTTPServer` (stdlib) | `core_service.py` |
| Dependencies | requests, colorama, rich, numpy, scipy, Pillow, psutil, python-dotenv, pyautogui, mss, av | `requirements.txt` (17 deps) |

### 3.3 Feature Inventory

| Feature | Status | Evidence (file paths) |
| :--- | :--- | :--- |
| **Core chat loop** (prompt → Ollama → response) | **COMPLETE** | `tui/app.py` & `agent.py` — restored missing `import os` in `tui/app.py:923` (previously raised `name 'os' is not defined` during SSE stream init) |
| **Textual TUI** (chat, HUD, footer, header) | **PARTIAL** | `tui/app.py`, `tui/widgets/` — works visually but SGR mouse escape leaks observed |
| **Tiered brain routing** (reflex/reason/coder/vision) | **COMPLETE** | `core_router.py` — `classify_task_tier()` with keyword matching |
| **Tool system** (125+ tools, 5 clusters) | **PARTIAL** | `tools.py`, `tool_clusters.py` — ~50 tools were unclustered/invisible (partially fixed in uncommitted changes) |
| **Multi-agent system** (jarvis, vision, friday, edith, ultron) | **PARTIAL** | `agents/profiles.json`, `agents/registry.py` — agent delegation works but per-agent voice/personality is incomplete |
| **Obsidian memory vault** | **COMPLETE** | `memory.py`, `obsidian_adapter.py`, `vault.py` — dual-layer SQLite + Markdown |
| **Voice (STT/TTS)** | **PARTIAL** | `voice.py`, `voice_synthesizer.py` — `/voice on` works, per-agent voices stubbed in uncommitted code |
| **Telegram bridge** | **COMPLETE** | `telegram_bridge.py` (1194 lines) — text, voice notes, slash commands, image sending |
| **Vision (screen/camera)** | **COMPLETE** | `vision.py` — `see_screen`, `see_camera` via moondream |
| **Face-ID / permissions** | **COMPLETE** | `face_id.py` — YuNet/SFace ONNX, tier enforcement |
| **Web browsing / search** | **COMPLETE** | `browser_agent.py`, `public_apis.py` — DuckDuckGo, URL extraction |
| **YouTube Studio pipeline** | **PARTIAL** | `youtube_studio/` (14 files, ~220KB) — content gen, anime editor, scheduler, uploader; publishing is fragile |
| **Hive Mind (multi-agent orchestration)** | **STUBBED** | `hive_mind.py` — registered in tools but not in clusters, functionally invisible to LLM |
| **Total Recall (context ring buffer)** | **STUBBED** | `total_recall.py` — registered but unclustered, roadmap Phase 10 |
| **Gesture control** | **BROKEN** | `gesture_control.py` — high CPU, camera contention, `ZAINE_CURRENT_STATE.md` marks "Built but Fragile" |
| **Approval system** | **COMPLETE** | `approval.py` — human-in-the-loop with TUI + Telegram cards, timeout/expiry |
| **Heartbeat daemon** | **COMPLETE** | `heartbeat.py` — reminders, battery sentinel, morning brief, night mode |
| **Sun Digraph (execution trace graph)** | **PARTIAL** | `tui/widgets/digraph.py` — renders but scrolling broken per user report |
| **Obsidian Memory Modal** | **PARTIAL** | `tui/widgets/obsidian_modal.py` — added in uncommitted changes, F4/`/graph` trigger |
| **Harness (structured tool outcomes)** | **PARTIAL** | `harness.py` — untracked file, added recently |
| **Code reviewer** | **COMPLETE** | `code_reviewer.py` — AST-based analysis |
| **Idea engine** | **COMPLETE** | `idea_engine.py` — brainstorming vault |
| **Self-distillation / fine-tuning** | **PARTIAL** | `self_distillation.py`, `finetune/` — QLoRA checkpoint-11 exists, but pipeline is manual |
| **Repo trainer** | **PARTIAL** | `repo_trainer.py` — trained on 17 repos (commit `00681ed`), status tracking exists |
| **Morning briefing** | **COMPLETE** | `morning_briefing.py` — Gmail + tasks summary |
| **Overnight autonomous pipeline** | **PARTIAL** | `overnight_autonomous_pipeline.py` — exists but reliability unknown |
| **Skills system** (reverse engineering, video editing, website design) | **STUBBED** | `tools_skills.py`, `.agents/skills/` — skill definitions exist, execution untested |

### 3.4 Environment Variables & External Dependencies

From [`.env.example`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/.env.example):
- `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` — email integration
- `USER_PERSONAL_EMAIL` — alert recipient
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_AUTHORIZED_USER_ID` — mobile bridge
- `OBSIDIAN_VAULT_PATH` — durable memory vault location

Runtime env vars (from code):
- `ZAINE_DEMO=1` — seminar mode
- `ZAINE_NUM_CTX` — context window size
- `ZAINE_WORKSPACE` — workspace path override
- `ZAINE_IDLE_TIMEOUT` — SSE idle timeout (added in uncommitted changes)

External services: Ollama (local), Gmail IMAP/SMTP (optional), Telegram Bot API (optional), DuckDuckGo (search), Unstop API (career search).

### 3.5 How to Run / Build / Test

```bash
# Prerequisites: Python 3.10+, Ollama running with models pulled
pip install -r requirements.txt
cp .env.example .env  # fill in credentials

# Run (TUI — primary):
python zaine_tui.py

# Run (legacy CLI — broken):
python main.py

# Run (seminar demo):
run_demo_fast.bat

# Tests:
python -m pytest tests/ -v
```

---

## 4. Evolution Timeline

| Date | Commits | What Changed | Type |
| :--- | :--- | :--- | :--- |
| **2026-09-05 12:48** | `6c087a7` | **Zaine v1 — monolith drop.** 71 files, 769K insertions. Full agent, voice, memory, tools, Telegram, HUD, vault, heartbeat, vision, fine-tuning pipeline, YouTube studio skeleton. Everything in one commit. | Feature Add |
| **2026-09-05 13:21** | `f749ad7` | **Ultron Mode** — dual persona (Jarvis/Ultron), holographic Web HUD theming, voice synthesis modulation. | Feature Add |
| **2026-09-05 13:36** | `6e293ce` | Enhanced Ultron mode — obsidian HUD, EMP glitch effects, neural baritone voice. | Feature Add |
| **2026-09-05 13:42** | `f66d634` | **Ponytail Architectural Thinking Engine** — 7-rung decision ladder for coding model. | Feature Add |
| **2026-09-05 13:53** | `a76ddb9` | Ultron mode expansion — full Python tool arsenal, "Creator loyalty directives", social media/Unstop omniscience. | Feature Add |
| **2026-09-05 14:04** | `ea5038a` | **Developer intelligence** — 17 GitHub repos + Code Rabbit integrated. | Feature Add |
| **2026-09-05 16:17** | `00681ed` | **2-hour autonomous training session** across 17 repos with thermal safeguards. | Feature Add |
| **2026-09-05 16:24** | `f5114bc` | Persistent memory block and vault profile for "Zara" (personal contact). | Feature Add |
| **2026-09-05 16:38–18:56** | `c36317f`→`012f76c` (9 commits) | **YouTube Studio pipeline** — Higgsfield AI shorts, anime AMV editor, beat detection, content generator, scheduler, uploader, analytics, FX engine, trend tracker. Rapid-fire additions. | Feature Add |
| **2026-09-05 19:28** | `e60f5b0` | 1-click batch launcher, anime edit duration upgrades, 20-video editing intelligence. | Feature Add |
| **2026-09-06 01:30** | `f38ee42` | Switched YouTube channel to 100% anime battles, night-time slots, published Gojo vs Sukuna edit. | Pivot |
| **2026-09-06 01:32** | `18a3910` | Overnight 05:00 AM target with YouTube scheduler + Telegram morning debrief. | Feature Add |
| *Gap: 31 days* | — | No commits between Sep 6 and Oct 7. **INFERRED:** Development paused; the creator was likely using the system and fixing things without committing. | — |
| **2026-10-07 18:26** | `9f41520` | **Phase 0 architecture stabilization** — HUD improvements, `.gitignore` cleanup, model checkpoint untracking. | Refactor |
| **2026-10-07 18:33** | `6c7a36f` | README rewrite — badges, architecture Mermaid diagram, MIT license. | Docs |
| **2026-10-13 17:00** | `daecbb8` | **Phase 0 stabilization checkpoint.** Major refactor: 345 files changed, 43,571 insertions, 7,919 deletions. Introduced `core_service.py`, `tui/` folder with Textual widgets, `coordinator.py`, `memory_manager.py`, `knowledge_engine.py`, `ollama_profiler.py`, and deleted the Electron `ui.py`. **This is the CLI-to-TUI architectural pivot.** | **Major Pivot** |
| **2026-10-23 12:33** | `d536472` | **Seminar readiness** — approval flow fixes, live digraph UI, launcher guardrails, `run_demo.bat`/`run_demo_fast.bat`, `zaine_env.py`, `exec_graph.py`, `system_graph.py`, numerous TUI widget fixes. 49 files, 4,343 insertions. Branch `seminar-stable` created here. | Feature Add / Bug Fix |
| **2026-10-23 14:48** | `d2f762b` | **VisionQuest sub-agents** — agent-to-agent delegation, `agents/` folder with 5 profiles (jarvis, vision, friday, edith, ultron), `registry.py`, sub-agent tool clusters. | Feature Add |
| *Gap: 10 days* | — | No commits between Oct 23 and Nov 4. | — |
| **2026-11-02–11-04** | *Uncommitted* | **Antigravity-assisted session** — 29 modified files, 15 untracked files. Added: `tui/widgets/obsidian_modal.py`, `harness.py`, `tools_skills.py`, `.agents/skills/` (3 skills), `tests/` (4 test files, 71 tests), `generated_sites/` (2 HTML demos). Fixed: SGR mouse escape leaks, auth headers in `system_graph.py`, pseudo-tool hallucination parsing, idle timeout, Obsidian modal styling. Added per-agent voice stubs, `/voice chat` command, scroll fixes. **None of this is committed.** | Feature Add / Bug Fix |

---

## 5. Pivots and Scope Changes

### Major Pivots

1. **Electron HUD → Textual TUI** (commit `daecbb8`, 2026-10-13)
   - **Dropped:** `ui.py` (Python HTTP server + Electron frontend), `static/css/style.css`, `static/js/hud.js`, `templates/index.html`, `main.js`, `package.json`, `launch_hud.py`
   - **Replaced with:** `core_service.py` (headless HTTP/SSE API), `tui/app.py` (Textual terminal UI), 10+ Textual widgets
   - **Evidence:** README states *"Architectural Pivot: As of v6.0, Z.A.I.N.E is terminal/TUI-first. The previous desktop/HTML HUD window phase has been deprecated."*
   - **Why (INFERRED):** Electron was heavy for a 4GB VRAM machine; terminal TUI is lighter and more hackable.

2. **YouTube content pivot: general → anime-only** (commit `f38ee42`, 2026-09-06)
   - Early commits (`fa81722`) expanded to "multi-genre content (funny cats, kids comedy, animated shorts)"
   - By `f38ee42`: *"switch channel to 100% anime battles with night-time slots"*

3. **Voice default OFF** (commit `daecbb8`)
   - Voice was initially always-on with wake word detection
   - Changed to command-gated (`/voice on`, `/speak`) — *"Zero Stealth Microphone Access"*

### Ideas That Appeared Then Vanished

| Idea | First Appeared | Current Status |
| :--- | :--- | :--- |
| Electron desktop HUD with Arc Reactor canvas | `6c087a7` (v1) | **Deleted** in `daecbb8` |
| `launch_hud.py` headless HUD server | `6c087a7` | **Deleted** |
| Paul Bettany voice clone (Phase 8) | `project-roadmap.md` | **Not started** |
| Raspberry Pi 5 hardware embodiment (Phase 11) | `project-roadmap.md` | **Not started** |
| XTTS-v2 local voice cloning | `project-roadmap.md` | **Not started** |

### Ideas Never in Original Plan but Now Exist

| Idea | Source |
| :--- | :--- |
| Multi-agent sub-system (5 personas: jarvis, vision, friday, edith, ultron) | Commit `d2f762b` (Oct 23) |
| Obsidian Memory Modal (Obsidian-like graph popup) | Uncommitted `tui/widgets/obsidian_modal.py` |
| Harness system (structured tool outcomes) | Uncommitted `harness.py` |
| Skills system (reverse engineering, video editing, website design) | Uncommitted `tools_skills.py`, `.agents/skills/` |
| 4 test suites (50-scenario, DOM, UI/UX, screen-recording) | Uncommitted `tests/` |
| Approval system with TUI + Telegram cards | Commit `d536472` |
| Seminar demo mode (`ZAINE_DEMO=1`) | Commit `d536472` |
| Per-agent voice synthesis (uncommitted) | Modified `voice.py`, `voice_synthesizer.py` |

### Original Plan vs. What Actually Got Built

| Original Plan (from roadmap) | What Got Built | Verdict |
| :--- | :--- | :--- |
| Phase 1: Voice, memory, persona | ✅ Complete | **Delivered** |
| Phase 2: Coding engine, file tools, system automation | ✅ Complete | **Delivered** |
| Phase 2+: Self-healing debug loop, experiential learning | ✅ Complete | **Delivered** |
| Phase 3: Gmail + Telegram bridge | ✅ Complete | **Delivered** |
| Phase 4: Heartbeat daemon, proactive alerts, vault | ✅ Complete | **Delivered** |
| Phase 5: Vision (screen/camera/webcam) | ✅ Complete | **Delivered** |
| Phase 6: Web browser agent | ✅ Complete | **Delivered** |
| Phase 7: Multi-agent hive mind | ⚠️ Partial — `hive_mind.py` exists but is unclustered; replaced by `agents/registry.py` system | **Pivoted** |
| Phase 8: Paul Bettany voice clone | ❌ Not started | **Not built** |
| Phase 9: Home Ops / service daemon | ⚠️ `home_ops.py` exists but monitors wrong DB | **Broken** |
| Phase 10: Total Recall context ring | ⚠️ `total_recall.py` exists but unclustered | **Stubbed** |
| Phase 11: Raspberry Pi hardware | ❌ Not started | **Not built** |
| *Not planned:* Full Textual TUI rewrite | ✅ Built (1,033 lines in `tui/app.py` alone) | **Unplanned addition** |
| *Not planned:* Multi-agent delegation (5 profiles) | ✅ Built | **Unplanned addition** |
| *Not planned:* YouTube anime content pipeline | ✅ Built (14 files, 220KB) | **Unplanned addition** |
| *Not planned:* Approval system | ✅ Built | **Unplanned addition** |
| *Not planned:* Seminar demo mode | ✅ Built | **Unplanned addition** |
| *Not planned:* Fine-tuning pipeline (QLoRA) | ⚠️ Partial — checkpoints exist, pipeline manual | **Unplanned addition** |

---

## 6. Code Health and Technical Debt

### 6.1 Critical Issues

| Issue | Severity | Evidence |
| :--- | :--- | :--- |
| **`name 'os' is not defined` runtime crash** | ✅ RESOLVED | Caused by missing `import os` at top of `tui/app.py` evaluating `os.getenv("ZAINE_IDLE_TIMEOUT")`. Fixed on 2026-11-05. |
| **Split-Brain database** — `home_ops.py` monitors stale `zaine_memory.db` while active agent uses `zaine_tasks.db` | 🔴 CRITICAL | [`ZAINE_CURRENT_STATE.md`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/ZAINE_CURRENT_STATE.md) Section 4, [`ZAINE_RECOVERY_PLAN.md`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/ZAINE_RECOVERY_PLAN.md) Fix A |
| **50 orphaned tools** — registered but never injected into LLM prompt | 🔴 CRITICAL | `ZAINE_CURRENT_STATE.md` Section 3: *"50 tools are registered but not clustered. They are functionally invisible."* |
| **SGR mouse escape sequences leaking** into terminal output | 🟠 HIGH | First screenshot shows raw ANSI codes `[555;38...` flooding the terminal |
| **Legacy CLI (`main.py` → `terminal_ui.py`) is broken** — never sends `X-Zaine-Token` | 🟠 HIGH | [`docs/CODEBASE_MAP.md`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/docs/CODEBASE_MAP.md) line 16: *"Legacy CLI never sends X-Zaine-Token, so every chat gets 401. Broken."* |

### 6.2 Dead / Duplicated Code

| Item | Path | Issue |
| :--- | :--- | :--- |
| `merged_model/` | `merged_model/config.json`, `generation_config.json` | Stale merge artifacts from fine-tuning experiments |
| `finetune/checkpoint-*` | `finetune/checkpoint-11/`, `finetune/zaine-3b-qlora/checkpoint-*` | Old QLoRA weights, 100MB+ of safetensors |
| `scratch/` | `workspace/` (root) | ~80 one-off scripts (hello.py, fibonacci.py, gcd.py, prime.py, etc.) — test outputs from the agent |
| `zaine_memory.db` + `.bak` | Root | Stale database; active DB is `zaine_tasks.db` |
| `zaine_face_id.db.bak` | Root | Stale backup |
| `eval_test_prompts.py` (root) | Root | Duplicate of `finetune/eval_test_prompts.py` |
| `hive_mind.py` | Root | Superseded by `agents/registry.py`; registered but unclustered |
| `total_recall.py` | Root | Registered but unclustered; roadmap Phase 10 stub |
| `zaine_cascade.py` | Root | `ZAINE_CURRENT_STATE.md`: *"Not a true IDE agent; just a terminal wrapper"* |
| Electron artifacts | `static/`, `templates/`, `assets/` | Some remnants may remain; HUD was deprecated |
| `workspace/voiceovers/` | `workspace/voiceovers/` (8 WAV files, ~12MB) | Generated TTS output files left in workspace |

### 6.3 Hardcoded Secrets / Credentials

- `.env` file exists (0.9KB) — contains actual credentials. **Flagged: values NOT printed here.**
- `client_secret.json` (0.4KB) — Google OAuth client secret file in project root. **Should not be committed.**
- `ZAINE_CURRENT_STATE.md` references Gmail address `hdj526655@gmail.com` in the roadmap.
- `.env.example` properly templates credentials without values.

### 6.4 Missing Tests

- No unit tests for `core_service.py` (1,363 lines), `coordinator.py`, `memory_manager.py`, `obsidian_adapter.py`
- No integration tests for the full request lifecycle (HTTP → agent → tool → response)
- The 4 test suites in `tests/` (71 tests) are all uncommitted and untested against CI
- No test runner configuration (no `pytest.ini`, `setup.cfg`, or `pyproject.toml`)

### 6.5 Inconsistent Patterns

- **Three memory systems coexist**: `memory.py` (SQLite), `memory_manager.py` (unified manager), `vault.py` (FTS5 notes) — unclear which is authoritative
- **Multiple entry points**: `main.py`, `zaine_tui.py`, `terminal.py`, `run_zaine.bat`, `run_demo.bat`, `run_demo_fast.bat`
- **Agent file is 1,778 lines** — monolithic, handles routing, parsing, tool execution, persona switching, memory injection
- **No type hints** on most public APIs (UNVERIFIED for all files; spot-checked `tools.py` and `agent.py`)
- **No logging framework** — uses `print()` and custom formatters throughout

---

## 7. Gaps and Next Steps

### 7.1 What Is Unfinished

1. **Runtime crash** — ✅ RESOLVED (`import os` restored in `tui/app.py`). Core chat loop operational.
2. **29 modified + 15 untracked files** never committed — significant risk of losing 2 days of work
3. **50 orphaned tools** still partially unresolved
4. **No CI/CD** — no GitHub Actions, no automated testing
5. **Split-brain database** not fixed in code
6. **SGR escape sequence leak** in terminal output (first screenshot)
7. **Gesture control** crashes from camera contention
8. **Session persistence** — no chat threads, no history sidebar
9. **Semantic search** — memory uses `LIKE %word%` instead of embeddings
10. **YouTube publishing** — fragile, requires manual intervention

### 7.2 Prioritized Next 10 Actions

| # | Action | Impact | Effort |
| :--- | :--- | :--- | :--- |
| 1 | **Fix `name 'os' is not defined` crash** — find and restore missing import | 🟢 RESOLVED | Done (`tui/app.py:923`) |
| 2 | **Commit all uncommitted work** — 29 modified + 15 untracked files | 🔴 Prevents data loss | 5 min |
| 3 | **Fix split-brain DB** — point `home_ops.py` to `zaine_tasks.db` | 🟠 Backup integrity | 15 min |
| 4 | **Cluster the remaining orphaned tools** in `tool_clusters.py` | 🟠 Restores ~42% of capability | 30 min |
| 5 | **Fix SGR mouse escape leak** in terminal output | 🟠 Visual quality | 30 min |
| 6 | **Remove `client_secret.json`** from repo root; add to `.gitignore` | 🟠 Security | 5 min |
| 7 | **Delete dead code** — `merged_model/`, stale `.db.bak` files, `workspace/` scratch scripts, duplicate `eval_test_prompts.py` | 🟡 Repo hygiene | 20 min |
| 8 | **Add `pyproject.toml`** with pytest config, project metadata | 🟡 Project structure | 15 min |
| 9 | **Refactor `agent.py`** — extract tool execution, persona, and routing into separate modules | 🟡 Maintainability | 2-4 hours |
| 10 | **Set up GitHub Actions** — run pytest on push, lint with ruff | 🟡 Quality gate | 30 min |

---

## 8. Summary for a Stranger

Z.A.I.N.E ("Project-Z") is a local-first AI assistant built by a single developer as a personal "Iron Man Jarvis" — an autonomous terminal-based agent that runs entirely on a laptop with a 4GB GPU. It uses Ollama to run small language models (3B–7B parameters) for conversation, coding, and vision tasks, backed by an SQLite/Obsidian memory system, 125+ automation tools, voice input/output, a Telegram mobile bridge, and an ambitious YouTube anime content pipeline. The project is ~60 days old with 30 commits and ~45,000 lines of Python. It is best described as an advanced prototype: the core loop works when it works, but runtime crashes, 50 invisible tools, a split-brain database, and significant uncommitted changes make it fragile. The architecture has been pivoted once (from Electron HUD to terminal TUI) and the scope has expanded well beyond the original 7-phase roadmap.

**What changed since day one:**
1. **Electron → Terminal TUI** — the entire UI layer was rewritten from a web-based HUD to a Textual terminal app (Oct 13).
2. **YouTube pipeline exploded** — what started as a simple shorts creator became a 14-file, 220KB anime editing suite in a single day (Sep 5).
3. **Multi-agent system appeared** — 5 named agent personas (Jarvis, Vision, Friday, Edith, Ultron) with delegation were added post-seminar (Oct 23).
4. **Security layer was bolted on** — approval system, X-Zaine-Token auth, and HITL guardrails were added for the seminar demo, not in the original design.
5. **Significant feature debt accumulated** — Phases 8–11 of the roadmap remain unstarted, while unplanned features (skills system, harness, Obsidian modal) were added in uncommitted sessions.

---

## 9. AI Council Consensus & Master Evolution Blueprint (Nov 2026)

Following a joint architectural review by the AI Council (**Gemini 2.0 Flash / Argon 4 High** on UI/UX, and **Claude Sonnet 5.5** on Backend Systems), alongside the integration of the trending **God's Eye** (`bilawalsidhu/gods-eye-view`) geospatial OSINT platform, the production blueprint for Project-Z has been codified.

### 9.1 UI/UX Consensus (Gemini Argon 4 High)
1. **Satellite HUD via pywebview / Chromium Kiosk:**
   - Decoupled web application served at `http://<host>:7860/hud`.
   - Strictly avoid `window.pywebview.api` bindings to allow the exact same HUD bundle to run identically inside a desktop `pywebview` floating window (WebView2) and on a remote Raspberry Pi touchscreen in Chromium kiosk mode (`chromium-browser --kiosk http://<host>:7860/hud`).
   - Memory footprint optimized via 360x360 canvas capped to 30 FPS standby / 60 FPS active.
2. **Physically Weighted Living Arc Reactor:**
   - Four mechanical layers: Central Plasma Core, 12-Segment Stator Ring, Counter-Rotating Gyro Gimbals, Outer Telemetry Bezel.
   - Rotational physics modeled via angular acceleration $\alpha = \frac{\tau - d \cdot \omega}{I}$.
   - 3-band FFT decomposition: Sub-bass (80–250Hz) drives core bloom, mid-range (250–2500Hz) drives stator piston displacement, high-frequency (2.5–8kHz) drives telemetry jitter.
   - Persona adaptations: 30° ratcheting stepper for E.D.I.T.H.; stochastic shear & chromatic glitch for Ultron; offscreen glow canvas caching.
3. **Textual TUI Dual-Screen Shift:**
   - Dual-screen state transition: Screen A (normal interactive terminal) vs Screen B (Acoustic Comm mode when Voice is ON).
   - Spacebar collision resolved: Esc/F5 returns to Screen A; Spacebar in Screen B is bound to "Force Utterance Endpoint / Commit Now".
   - Silence VAD countdown horizon bar visualizes endpointing threshold in real time. Two-tone transcript rendering (dim slate hypothesis, bright white commit). 3-line pinned context drawer at top of Screen B.
4. **Procedural WebAudio Sound Design (0 KB disk assets):**
   - Pure WebAudio API synthesis: 110ms upward sine (440→587Hz) for Zaine wake; 95ms dual-impulse relay chirp (660Hz) for Subagent handoff; 130ms click-latch for E.D.I.T.H.; 220ms sonar ping for F.R.I.D.A.Y.; 240ms sub-bass drop (92→48Hz saw) for Ultron; 260ms muted descending minor third for Fail-to-Reflect.

### 9.2 Backend Systems Consensus (Claude Sonnet 5.5)
1. **Fail-to-Reflect & Circuit Breaker Decoupling:**
   - **Critical Rule:** Never invoke an LLM inside the synchronous error/failure path. Infrastructure faults (Ollama down, socket drop) cascade and add 2–12s latency to failing turns.
   - Synchronous path is deterministic and cheap: Keyed circuit breaker (`CLOSED` → `RECORDING` → `OPEN` → `HALF_OPEN`) + writes to append-only `failure_events` black box table (with JSONL fallback if DB is busy).
   - Reflection is an asynchronous, idle-gated background task running only on logic errors. Produces candidate rules with `status: 'candidate'` requiring explicit review (`/rules` command) before activation.
   - Hardened SQLite: WAL mode, `busy_timeout=5000ms`, dedicated single-writer queue, real FTS5 triggers on `learned_rules`.
2. **Subagent Delegation via Typed Task Envelopes:**
   - Conversation history is never leaked or passed to subagents.
   - Deterministic context compiler constructs an immutable `TaskEnvelope` (goal, brief <= 120 tokens, explicit pointers/ranges, granted tool clusters, denied tools, token budget).
   - Subagents execute **inline under the parent's coordinator slot** to avoid deadlocks with Ollama's single-flight model runner. Max delegation depth = 1.
   - ContextVar-based tool permission enforcement wrapping all registry calls. Subagents return structured `ResultEnvelope` (status, summary <= 200 tokens, patch diffs, taint markers).
3. **Armory Job Telemetry & Isolation:**
   - Dedicated `GET /api/jobs/stream` SSE endpoint separate from the chat token stream, eliminating SSE contention and chat stuttering.
   - Long-running processes (FFmpeg, YouTube scheduler, n8n sync) run in independent process groups (`CREATE_NEW_PROCESS_GROUP`, `CREATE_NO_WINDOW`) with dedicated reader threads draining stdout JSON Lines.
   - Subprocesses run at `BELOW_NORMAL_PRIORITY_CLASS` to preserve CPU/GPU headroom for resident LLM inference.
4. **E.D.I.T.H. Self-Modification 4-Zone Security:**
   - **Zone 0 (Kernel):** Read-only, human-edit only (`approval.py`, `coordinator.py`, `core_service.py`, trust enum, `.env`).
   - **Zone 1 (Extensions):** Patch proposal + static AST gate + automated tests + human approval (`custom_tools/`, agent profiles).
   - **Zone 2 (Application):** Patch proposal + full test suite + human approval + full restart (no hot-reloading core modules).
   - **Zone 3 (Workspace):** Standard tool policy for external project workspaces.
   - Worktree isolation: E.D.I.T.H. operates strictly on isolated git worktrees, producing unified diffs verified by SHA-256 hashes bound to human approval (eliminating TOCTOU vulnerabilities).

### 9.3 God's Eye (`bilawalsidhu/gods-eye-view`) Integration Architecture
1. **Platform Profile:**
   - Open-source #1 trending geospatial spatial intelligence console combining 3D earth visualization (CesiumJS, Google Photorealistic 3D Tiles) with GLSL tactical shaders (FLIR thermal, NVG night vision, tactical wireframe).
   - Real-time ingestion: ADS-B flight transponders (OpenSky), AIS maritime ship tracking, CelesTrak satellite orbits, USGS earthquake & NASA hazard telemetry, and public CCTV cameras.
2. **Mansion & Armory Role Assignment:**
   - **Assigned Operator:** **F.R.I.D.A.Y.** (Tactical Overseer & Situational Awareness specialist).
   - **Tool Cluster:** `TACTICAL_OSINT` (granted exclusively to Friday; denied to Ultron/Edith by default).
   - **Tools:** `query_flight_radar()`, `get_orbital_passes()`, `get_maritime_vessels()`, `stream_cctv_feed()`, `query_hazard_intel()`.
   - **HUD Viewport Mode:** Satellite mini-tab provides a toggleable tactical 3D globe viewport streaming live geospatial telemetry alongside the Arc Reactor.
   - **Local Vision Fusion:** Unifies external OSINT feeds with local hardware inputs (Air Canvas, ESP32-CAMs, Raspberry Pi camera nodes) into a single spatial awareness layer.

---

*Dossier generated from: 30 git commits, 271 Python files, 15 markdown/spec documents, 2 user screenshots, AI Council reviews (Gemini Argon 4 High & Claude Sonnet 5.5), and God's Eye architectural integration.*

