# Z.A.I.N.E Architectural Migration Record: Desktop GUI to Terminal-Native Agent

**Date:** October 2026  
**Status:** Completed  
**Subject:** Full Architectural Pivot from Desktop/Web GUI to Terminal/TUI-First Autonomous AI Agent

---

## 1. Executive Summary

Z.A.I.N.E has been re-architected from an application/UI-oriented desktop experience (Electron, Web HUD on port 7860, Chrome `--app` mode, background microphone wake-word listening) into a **terminal-native, autonomous AI developer and companion agent**.

The terminal is no longer one peripheral interface among several; **the terminal is now the primary, authoritative, and singular user interface for Z.A.I.N.E.**

The desktop GUI phase has been deprecated and removed from the active execution path. Voice conversation is now **explicitly disabled by default** and will never activate unprompted during text interactions.

---

## 2. Architectural Comparison

### OLD Architecture (v1.0 - v5.0 GUI Phase)
```text
                    Desktop Window / Electron / Web HUD
                                     │
                                     ▼
                      ui.py (HTTP + HTML/CSS/JS Assets)
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
             Continuous Mic / VAD               ZaineAgent
             (Always Listening)                       │
                                           ┌──────────┴──────────┐
                                           ▼                     ▼
                                      Brain Router             Tools
```
- Launching `python main.py` or `python launch_hud.py` opened desktop browser windows (`--app` flag, Electron shells, or Acrylic HUDs).
- Voice engine auto-bound to microphone input and Piper TTS on launch; spoke responses out loud by default.
- Terminal UI (`terminal_ui.py`) was a secondary wrapper depending on an active UI server.

### NEW Architecture (v6.0 Terminal-Native Agent)
```text
                         ┌───────────────────┐
                         │   Z.A.I.N.E. CLI  │
                         │      / TUI        │
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │   Command Router  │
                         │ Natural Language  │
                         │ Slash Commands    │
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │   Core Agent      │
                         │  (core_service)   │
                         └─────────┬─────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
        Brain Router          Tool System           Memory
              │                    │                    │
       ┌──────┼──────┐             │             ┌──────┴──────┐
       ▼      ▼      ▼             ▼             ▼             ▼
     Qwen   DeepSeek Coder      119+ tools    SQLite       Obsidian
       │                                                 (Durable Vault)
       ▼
     Vision

                    Optional Integrations
                           │
                    ┌──────┴──────┐
                    ▼             ▼
                 Telegram       Voice (Explicit Command Only)
                                (Default: VOICE_DISABLED)
```

---

## 3. What Was Removed / Retired

1. **Desktop Window Launchers:**
   - `launch_window()` in `ui.py` is neutralized into a safe no-op.
   - Chrome `--app` mode, edge webview wrappers, and Electron startup are removed from the active runtime.
   - `launch_hud.py` is deprecated with a redirection warning directly launching `run_terminal_cli()`.
2. **Automatic Microphone / Voice Loop:**
   - Microphone initialization at startup is removed.
   - Automatic wake word listening loop in `wakeword.py` is stopped from auto-booting on start.
   - Unwanted Piper/Edge-TTS vocalization on text responses is eliminated: `voice.speak_sentence()` immediately returns if voice mode is not enabled.
3. **GUI Dependency Coupling:**
   - Core agent logic no longer requires Flask/HTML templates or static frontend bundles.
   - `core_service.py` provides a clean, headless multi-threaded HTTP/SSE API without HTML rendering.

---

## 4. What Was Migrated & Created

1. **Headless Core Agent Service (`core_service.py`):**
   - Encapsulates Layer 2: `ZaineAgent` lifecycle, `RequestCoordinator`, SSE streaming (`/api/chat/stream`), telemetry, and REST endpoints.
   - Replaces `ui.py` as the system's headless daemon.
   - Backward compatibility shim maintained in `ui.py` for legacy imports.
2. **Deterministic Voice State Machine (`voice.py`):**
   - Thread-safe states: `VOICE_DISABLED` (default), `VOICE_ENABLED`, `LISTENING`, `PROCESSING`, `SPEAKING`.
   - Explicit commands: `/voice on`, `/voice off`, `/voice status`, `/speak`.
   - Lazy-loading of speech models (`Faster-Whisper` and `Piper-TTS`) to keep startup instant and save GPU/RAM.
3. **Rich Terminal User Experience (`terminal_ui.py`):**
   - Dynamic real-time status bar displaying Persona, Model, Voice State (`VOICE: OFF`), and Tool readiness.
   - Capability overview on startup detailing Brain Fleet, 119+ dynamic tools, and SQLite + Obsidian memory stats.
   - Persona-specific input prompts: `Sir ❯ ` (Jarvis) and `Creator ❯ ` (Ultron).
   - Clean, compact tool activity indicators (`[tool] filesystem.search`) without massive JSON dumps.
   - Direct integration with Code Mode (`zaine_cascade.py`) via `/code`, `/inspect`, `/run`, `/test`, `/files`.
4. **Canonical Entry Point (`main.py`):**
   - Boots `CoreService` in headless background daemon, starts background Telegram client & Heartbeat sentinel, guarantees `voice.disable_voice()`, and directly enters `run_terminal_cli()`.

---

## 5. What Was Preserved (Zero Functional Regression)

1. **Neural Model Fleet & Brain Router:**
   - Reflex Core: `qwen2.5:3b`
   - Reasoning Core: `deepseek-r1:7b`
   - Coding Core: `qwen2.5-coder:3b`
   - Vision Core: `moondream` (1.8B VLM)
   - Intelligent multi-tier routing via `core_router.py`.
2. **Tool Ecosystem:**
   - Full 119+ tool registry across 13 specialized tool clusters (`tool_clusters.py`, `tools.py`).
3. **Memory Subsystem (Hardened Obsidian + SQLite):**
   - Dual-layer storage: SQLite for fast runtime indexing + Obsidian Markdown vault for human-readable long-term durability.
   - Security boundaries: `MemoryPolicy`, prompt injection detection, trust level gating, XML isolation, and idempotency migrations.
4. **External Integrations:**
   - Pocket Zaine Telegram Bot (`telegram_bridge.py`).
   - System automation, vision, and hardware thermal guards.

---

## 6. How to Run Z.A.I.N.E. Now

### Canonical Launch
```bash
python main.py
```
Or via the Windows batch launcher:
```cmd
run_zaine.bat
```

### Standalone CLI Launch
If `main.py` is not running, launching `terminal_ui.py` directly will auto-initialize the headless `CoreService` in-process:
```bash
python terminal_ui.py
# or
python terminal.py
```

### Running Tests
To verify CLI decoupling and Voice isolation:
```bash
python -m unittest test_cli_architecture.py
```
To verify the durable memory subsystem:
```bash
python -m unittest test_memory_subsystem.py
```

---

## 7. Command Reference Summary

| Command | Action |
| :--- | :--- |
| `/help` | Display comprehensive command palette |
| `/status` | View system, hardware, model, and network telemetry |
| `/voice status` | Check voice state machine and audio engine readiness |
| `/voice on` | Explicitly enable persistent voice response mode |
| `/voice off` | Disable voice mode (return to text-only) |
| `/speak` | One-shot microphone query (speaks reply, then returns to text-only) |
| `/persona jarvis` | Switch persona to Jarvis (polite assistant, "Sir") |
| `/persona ultron` | Switch persona to Ultron (ruthless efficiency, "Creator") |
| `/memory stats` | View Obsidian vault structure and note counts |
| `/memory list` | List recent stored memories and preferences |
| `/memory search <q>`| Search knowledge vault with query |
| `/memory add <t>\|<c>`| Safely insert a new memory note into Obsidian vault |
| `/memory archive <id>`| Archive an outdated memory note |
| `/code <prompt>` | Invoke Qwen2.5-Coder for code synthesis |
| `/inspect <file>` | Inspect workspace file with line numbers |
| `/run <file>` | Execute Python script in workspace |
| `/test` | Run workspace unittest suite |
| `/files` | List project workspace files |
| `/session` | View current session parameters |
| `/new` | Start a new chat session (clears working context, keeps vault) |
| `/history` | View episodic memory summaries |
| `/clear` | Clear terminal screen and reprint banner |
| `/exit`, `/quit` | Gracefully shut down Z.A.I.N.E |
