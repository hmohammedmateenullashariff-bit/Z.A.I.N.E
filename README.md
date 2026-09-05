# Z.A.I.N.E — Autonomous Local AI Assistant & System Engineer

**Z.A.I.N.E** (*Zero-latency Autonomous Intelligent Neural Entity*) is a fully local, privacy-first, embodied AI assistant designed for Mateen. Running 100% offline via Ollama, Piper, Faster-Whisper, and DirectShow, Zaine bridges voice conversation, system control, multimodal vision, and remote mobile execution via Telegram.

---

## Architecture & Neural Models

| Engine | Model / Tool | Hardware / VRAM | Role |
| :--- | :--- | :--- | :--- |
| **Primary Persona** | `zaine:latest` (Customized Qwen2.5 3B) | 100% GPU VRAM | Conversational reasoning, tool orchestration, Jarvis persona |
| **Coder Engine** | `zaine-coder:latest` (Qwen2.5-Coder 3B) | 100% GPU VRAM | Local code generation, syntax repair, and terminal troubleshooting |
| **Multimodal Vision** | `moondream:latest` (1.8B VLM) | 100% GPU VRAM | Screen perception, webcam inspection, desk presence, Telegram photo OCR |
| **Speech-to-Text** | `Faster-Whisper` (base.en / tiny) | Local CPU/CUDA | Streaming wake word detection and voice command transcription |
| **Neural TTS** | `Piper-TTS` (en_GB-alan-medium) | Local CPU | Natural British voice with 0ms barge-in interruption |
| **Second Brain** | SQLite FTS5 + BM25 | Local Storage | Instant local retrieval across personal notes & knowledge |

---

## Core Capabilities (Shipped Phases 1–5)

### 1. Voice & Conversational Flow
- **Wake Word Activation:** Say *"Zaine"* to wake. Automatic follow-up listening for 10 seconds without needing the wake word.
- **Real-Time Barge-In:** Speak *"Zaine, stop"*, *"wait"*, or press any key to interrupt speech in **0.00ms**.
- **Dual Language Protocol:** Defaults to crisp, articulate English (Jarvis style). Automatically transitions to Hindi/Urdu when addressed in Hindi/Urdu.

### 2. Desktop Automation & Tool Use
- **App Launcher:** Launch any application, game, or tool (*"Open Discord"*, *"Open VS Code"*, *"Open YouTube"*).
- **Task Management:** SQLite-backed task manager (`add_task`, `list_tasks`, `complete_task`, `delete_task`).
- **Media Controls:** Skip ads, play/pause, volume mute, or auto-play music on YouTube.
- **Workspace Engineering:** Inspect code files, write scripts, edit snippets, run terminal commands, and launch local web servers.

### 3. Jarvis Timers & Proactive Heartbeat Daemon
- **Scheduled Alarms:** Relative (`"in 20 mins"`) and absolute (`"18:30"`) timer parser. Alarms ring aloud and dispatch alerts to your phone.
- **Battery Sentinel:** Notifies you via voice and Telegram when battery drops below 20% on battery power.
- **Daily Intelligence Briefings:** Morning summary of unread emails and tasks (08:00–11:30 AM); evening debrief and server sign-off (21:00–23:30 PM).
- **Smart Night Mode:** Whisper-quiet operation between 00:00 and 07:00 AM (mutes TTS, silent Telegram pushes only).
- **Ergonomics Sentinel:** Prompts for water and eye breaks after 90 minutes of continuous screen work.

### 4. Personal "Second Brain" (Vault)
- Local markdown notes stored in `vault/` with SQLite FTS5 full-text indexing and BM25 ranking.
- Search documents instantly via voice, console, or Telegram.

### 5. Multimodal Vision ("Eyes")
- **Screen Perception (`see_screen`):** In-memory display grab in RAM to diagnose error messages, analyze website layouts, or inspect code.
- **Webcam Inspection (`see_camera`):** 1-shot DirectShow hardware grab with instant device release (< 500ms LED on) to read physical documents or check real-world items.
- **Desk Presence Sentinel:** Local VLM recognizes when you return to your desk after being away (> 30 minutes) and welcomes you back.

### 6. Pocket Zaine (Remote Mobile Telegram Bridge)
- Connected to `@Zaine_mateen_bot` with strict user pairing and PIN authorization.
- **Slash Commands Menu:** Native autocomplete menu on mobile for `/status`, `/screen`, `/camera`, `/vault`, `/remind`, `/notes`, `/tasks`, `/emails`, and `/help`.
- **Bidirectional Multimodal Vision:** Send `/screen` or `/camera` to get snapshots from your laptop, OR send any photo from your phone for instant local Moondream visual analysis!
- **Voice Notes:** Send audio notes directly from Telegram; transcribed on the fly via Faster-Whisper.

---

## Quick Start Guide

### 1. Install Dependencies
Ensure [Ollama](https://ollama.com) is installed, then pull required models:
```bash
ollama pull qwen2.5:3b
ollama pull qwen2.5-coder:3b
ollama pull moondream
```

Install Python requirements:
```bash
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file in the project root:
```env
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_ALLOWED_USER_ID="1245854320"
TELEGRAM_PAIR_PIN="7860"
USER_PERSONAL_EMAIL="hmohammedmateenullahshariff@gmail.com"
EMAIL_ACCOUNT_ADDRESS="zaine.assistant@gmail.com"
EMAIL_APP_PASSWORD="your_gmail_app_password"
```

### 3. Launching Zaine

**Full Voice & GUI Assistant:**
```bash
python main.py
```

**Headless Remote Telegram & Proactive Daemon:**
```bash
python telegram_bridge.py
```

---

## Roadmap

- [x] **Phase 1:** Core Conversational Loop, Task Management & System Status
- [x] **Phase 2:** Advanced Tool Calling, Web Research & Local Coding Engine
- [x] **Phase 3:** Full Local Voice Loop, Wake Word & Neural TTS
- [x] **Phase 4:** Proactive Heartbeat, Real-Time Barge-In & Mobile Telegram Bridge
- [x] **Phase 5:** Vision & Multimodal Perception ("Eyes")
- [ ] **Phase 6:** Hardware Embodiment & Ambient Computing (Raspberry Pi 5, Chassis Display & Voice Cloning)
