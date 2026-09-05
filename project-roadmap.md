# Project Roadmap: Z.A.I.N.E (Zero-latency Autonomous Intelligent Neural Entity)

**Core Philosophy:** Software-first & security-first. Build, harden, and evaluate every capability on PC before hardware deployment. One unified pipeline, tool-first modularity, fine-tune only when necessary.

---

## ✅ Phase 1 — Core Voice, Intelligence & Persona Layer [SHIPPED]

- [x] **Zero-Disk In-Memory Transcription:** Migrated Faster-Whisper to in-RAM float32 numpy buffers (eliminated temporary WAV disk I/O).
- [x] **Sentence-Level Streaming TTS:** HTTP chunked streaming from Ollama with sentence parsing for sub-second Time-to-First-Audio (<1.0s).
- [x] **Dynamic Silence Endpointing (VAD):** Real-time RMS audio monitoring in 80ms windows; auto-cuts recording after ~900ms of silence.
- [x] **Audio Feedback Chime:** Harmonic two-tone earcon (587Hz -> 880Hz) on wake word detection ("Zaine").
- [x] **Persistent Long-Term Memory:** SQLite `memories` table with `remember` and `recall` tools surviving application restarts.
- [x] **Live Web Search:** Real-time web knowledge retrieval via DuckDuckGo and Wikipedia search API (zero paid API keys).
- [x] **Embodied Persona & Multilingual Adab:** Fine-tuned persona (Jarvis-style, philosophical, energetic, calm) with fluid English, Hindi, and Urdu (Hinglish) support.
- [x] **Upgraded Voice Engine:** High-energy, articulate British Jarvis neural voice (`en_GB-alan-medium`) with `0.92` pacing.

---

## ✅ Phase 2 — Autonomous "Vibe Coding" & System Automation [SHIPPED]

- [x] **Workspace Sandbox:** Dedicated safe execution environment in `workspace/` with directory traversal protection.
- [x] **File Tools:** `write_workspace_file`, `read_workspace_file`, and `list_workspace_files`.
- [x] **Code Execution Engine:** `run_python_script` executes code locally in `workspace/` with a 15-second timeout and stdout/stderr capture.
- [x] **Desktop App Control:** `open_application` launches desktop utilities (Chrome, VS Code, Spotify, Notepad, Calculator, Explorer).
- [x] **Hardware Telemetry:** `system_status` queries live CPU load, RAM utilization, and battery state via `psutil`.
- [x] **Multi-Tool ReAct Engine:** Agent parser handles multi-tool calls in a single turn with automatic argument and tool aliasing.
- [x] **Live YouTube & Media Controls:** `play_on_youtube`, `media_control` (ad skipping, next song, play/pause, mute), `close_application`, and Smart Idle Mode (bypasses follow-up listening so music isn't picked up).

---

## ✅ Phase 2+ — Autonomous Coder Engine & Continuous Experiential Learning [SHIPPED]

- [x] **Specialized Coding Co-Processor:** Integrated local `qwen2.5-coder:3b` via `code_assistant(prompt, context_code)` for optimal algorithm generation, refactoring, and complex troubleshooting.
- [x] **Targeted In-Place Code Editing:** Added `edit_workspace_file(filepath, target_snippet, replacement_snippet)` to safely edit functions without rewriting entire files.
- [x] **Workspace Terminal Execution:** Added `execute_command(command)` to run shell commands (`pip install`, `pytest`, `python ...`) strictly within the workspace sandbox.
- [x] **AST Code Architecture Inspector:** Added `read_code_definitions(filepath)` using Python AST to inspect classes, methods, and docstrings of workspace scripts.
- [x] **Autonomous Self-Healing Debug Loop:** If a script or command fails with an error or traceback, Zaine autonomously inspects the error, repairs the code, re-runs it, and verifies correctness before reporting to Mateen.
- [x] **Continuous Experiential Learning ("Learn-as-You-Code"):**
  - [x] SQLite `task_learnings` table storing acquired skills, debugging rules, and user preferences.
  - [x] Explicit skill learning via `learn_lesson(lesson, keywords)` tool.
  - [x] Dynamic context injection: Automatically retrieves relevant past lessons matching current user tasks and injects them into the system prompt.

---

## ✅ Phase 3 — Autonomous Communications & Remote Reach [SHIPPED]

- [x] **Dedicated Gmail Account (`hdj526655@gmail.com`):**
  - [x] Set up secure IMAP/SMTP credentials with Google App Password in `.env`.
  - [x] Implemented `check_emails(unread_only=True)` in `email_client.py` to fetch and summarize incoming emails.
  - [x] Implemented `send_email(to, subject, body)` to send outgoing emails from Zaine's address.
  - [x] Integrated into agent tool registry and conversational pipeline.
- [x] **"Pocket Zaine" (Private Mobile Telegram Bridge):**
  - [x] Lightweight native Telegram bot bridge (`telegram_bridge.py`) running in background.
  - [x] Connected to `@Zaine_mateen_bot` with token in `.env`.
  - [x] Strict user whitelist gatekeeper with `/pair <PIN>` pairing protection.
  - [x] Full text chat & tool calling execution over Telegram.
  - [x] Voice note decoding via local Faster-Whisper.
  - [x] Slash commands (`/status`, `/emails`, `/tasks`, `/clear`).
  - [x] Background daemon auto-start integration in `main.py`.

---

## ✅ Phase 4 — Proactive Intelligence & Natural Conversational Flow [SHIPPED]

- [x] **The "Proactive Heartbeat" Daemon:**
  - [x] Background daemon thread (`heartbeat.py`) monitoring alarms, battery, morning/evening briefs, storage, and ergonomics.
  - [x] Dual-channel proactive alerts: voice announcements on desktop + push alerts to Telegram (`@Zaine_mateen_bot`).
  - [x] **Jarvis Timers & Alarms (`set_reminder`):** Due timer scheduler triggers precise voice + Telegram alerts (`tools.py`).
  - [x] Battery Sentinel: < 20% warning with auto-cooldown.
  - [x] Daily Morning Briefing: Unread Gmail count + pending tasks briefing delivered once daily (8:00–11:30 AM).
  - [x] **Evening Debrief & Night Sign-Off:** Daily wrap-up + server cleanup reminder (21:00–23:30 PM).
  - [x] **Hardware Sentinel:** Low disk space (< 10GB free on C:) alerts.
  - [x] Ergonomics Sentinel: 90-minute continuous work & hydration reminder.
  - [x] **Smart Night Mode:** Whisper-quiet mode between 00:00 and 07:00 AM (mutes TTS, silent push only).
- [x] **Real-Time "Barge-In" (Audio Interruption):**
  - [x] Background microphone monitoring and keypress detection during voice playback and Piper synthesis.
  - [x] Instant 0ms audio cut-off when user speaks stop words (*"Zaine"*, *"stop"*, *"wait"*, *"ruko"*, *"chup"*) or hits key.
  - [x] Seamless sentence streaming break in `main.py` transitioning directly back to idle (skips annoying auto-listen; waits for wake word).
- [x] **Local "Second Brain" / Personal Vault (Local RAG):**
  - [x] Dedicated `vault/` directory with SQLite FTS5 (Full-Text Search) and BM25 ranking.
  - [x] Auto-syncs and generates human-readable `.md` notes.
  - [x] Tools: `search_vault`, `add_to_vault`, `list_vault_documents`, `set_reminder`, `list_reminders`, and `trigger_proactive_check`.
  - [x] **Mobile Telegram Commands:** `/vault <query>`, `/addnote`, `/remind`, `/reminders`, `/notes`.

---

## ✅ Phase 5 — Vision & Multimodal Perception ("Eyes") [SHIPPED]

- [x] **"See My Screen" (`see_screen`):**
  - [x] Fast desktop window capture via `PIL.ImageGrab` in RAM with sleep/lock fallback.
  - [x] Integration with lightweight local vision model (`moondream:latest` 1.8B running 100% GPU in Ollama).
  - [x] Autonomous tool calling: *"Look at my screen, what does this error mean?"*.
- [x] **Webcam Inspection (`see_camera`):**
  - [x] 1-shot webcam frame grab via `opencv-python` (DirectShow) with instant device release (< 500ms LED on).
  - [x] Real-world object, scene, and room inspection.
- [x] **Desk Presence Detection:**
  - [x] Detects when user returns to desk after being away (> 30 mins) via `heartbeat.py` sentinel.
  - [x] Personalized welcome greeting ("Welcome back, Sir. All systems standing by.").
  - [x] Strict privacy guard: 100% offline, in-memory RAM analysis, zero frames saved or streamed externally.
- [x] **Remote Mobile Vision via Telegram:**
  - [x] `/screen`: Sends live desktop capture photo to `@Zaine_mateen_bot`.
  - [x] `/camera`: Takes a 1-shot webcam photo and sends it to Telegram.

---

## ✅ Phase 6 — Autonomous Web Browser Agent ("Cyber Hands") [SHIPPED]

- [x] **Autonomous Web Extraction (`browse_web`):** Fetches and reads any public URL with realistic browser headers, stripping ads, scripts, and navigation boilerplate, with optional CSS selector targeting.
- [x] **Multi-Source Deep Research (`search_and_extract`):** Searches DuckDuckGo, visits the top result pages, and extracts structured source content for deep research rather than superficial search blurbs.
- [x] **Direct Web File Downloader (`download_web_file`):** Safely downloads datasets, CSVs, code files, and assets from the web directly into the `workspace/` sandbox with file sanitization and a 50MB safety guard.
- [x] **Zero-Cost & Local:** Built on `requests` and `beautifulsoup4` without expensive headless browser overhead or paid scraping APIs.

---

## 🚀 The Next 5 Software & Autonomous Intelligence Phases

## ✅ Phase 7 — Autonomous Multi-Agent Hive Mind [SHIPPED]

- [x] **Specialist Sub-Agents ([`hive_mind.py`](file:///c:/Users/Mohemad%20Mateen%20ullah/Documents/projects/Project-Z/hive_mind.py)):** Built cooperating sub-agents (`CoderSubAgent`, `ResearcherSubAgent`, `SystemGuardianSubAgent`, `ExecutivePlannerSubAgent`).
- [x] **Shared In-Memory Blackboard:** In-RAM artifact repository (`HiveBlackboard`) where sub-agents pass research data, generated code, and diagnostic telemetry.
- [x] **Executive Orchestrator Tool:** Bound `hive_mind(goal)` into `tools.py` and `agent.py` to autonomously decompose multi-step goals, coordinate sub-agents, and deliver unified briefings.
- [x] **Self-Healing LLM Tool Parsing:** Added resilient regex recovery in `agent.py` to prevent JSON formatting errors from trapping multi-agent execution in loops.

---

### ⏳ Phase 8 — True Paul Bettany Jarvis Neural Voice Cloning (Local Zero-Cost TTS)
- [ ] **Iconic Timbre:** Clone Paul Bettany's exact Iron Man Jarvis voice timbre using zero-cost local XTTS-v2 / fine-tuned neural acoustic checkpoint.
- [ ] **Inflection & Dynamic Cadence:** Modulate vocal pitch, warmth, and cadence based on dialogue urgency (calm in normal chat, alert in critical telemetry).
- [ ] **100% Offline & Zero-Latency:** Retain sub-second time-to-first-audio with streaming chunk synthesis and 0ms barge-in.

### ⏳ Phase 9 — Local Home & Developer Ops Orchestrator ("Home Ops")
- [ ] **Service Daemon Manager:** One-command launcher and watchdog for local development services, Docker containers, databases (PostgreSQL/Redis), and test servers.
- [ ] **Self-Healing Process Guardian:** Detects crashed background processes, checks exit codes, inspects logs, and auto-restarts failed services without user intervention.
- [ ] **Scheduled Automated Backups:** Automated nightly incremental backups of `zaine_memory.db`, `vault/`, and project files.

### ⏳ Phase 10 — Omnipresent Context & Audio-Visual Memory ("Total Recall")
- [ ] **Ephemeral 60-Minute Context Ring Buffer:** In-memory ring buffer tracking recent active windows, code files inspected, errors encountered, and audio topics discussed over the last hour.
- [ ] **Time-Travel Query Answering:** Ask *"Zaine, what was that error we saw 20 minutes ago on the screen?"* or *"What did we name that variable in the last file?"*
- [ ] **Zero-Disk Privacy:** All timeline frames and tokens expire and clear from RAM automatically; zero private screenshots saved to disk.

### ⏳ Phase 11 — Hardware Embodiment & Ambient Computing (Future Phase 6 on Hardware Availability)
- [ ] Raspberry Pi 5 Central Brain + Custom Touchscreen Chassis.
- [ ] Distributed ESP32-S3 Satellite Nodes with I2S mics throughout the room.

---

## Architectural Rules & Security Principles

1. **Security Sandbox:** Code execution and file operations must stay inside `workspace/`.
2. **Permission Guardrails:** Destructive actions (deleting data, sending external emails) require verbal confirmation.
3. **Secret Management:** Credentials (email passwords, Telegram tokens) strictly stored in `.env`, never in code.
4. **Compute Discipline:** Off-the-shelf models + targeted tooling first; fine-tune only when an off-the-shelf model demonstrably fails.
5. **Local Sovereignty:** 100% offline, zero-cost, zero subscription dependencies.
