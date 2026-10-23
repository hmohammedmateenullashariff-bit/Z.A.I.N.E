# Z.A.I.N.E Codebase Map & Readiness Audit (2026-10-22)

Built from a full read of all ~35,700 lines of Python, split into 7 subsystem reviews. The most surprising claims were spot-checked against the code by hand.
Status legend: ✅ fixed on 2026-10-22 · 🔴 critical · 🟠 high · 🟡 medium · ⚪ low.

---

## 1. How Zaine runs

### Entry points

| Launcher | What starts | Notes |
| :--- | :--- | :--- |
| `run_demo_fast.bat` / `run_demo.bat` | `core_service.py` in the background (same console), then `zaine_tui.py` | Seminar path. Fast mode = `zaine-fast-3b`, `ZAINE_NUM_CTX=6144`, `ZAINE_WORKSPACE=demo_workspace`. |
| `python zaine_tui.py` | Textual TUI. If no core is running, it starts `CoreService` **inside the TUI process**. | |
| `run_zaine.bat` → `main.py` | Agent + CoreService + heartbeat daemon + legacy Rich CLI (`terminal_ui.py`) | 🟠 Legacy CLI never sends `X-Zaine-Token`, so every chat gets 401. Broken. |
| `python telegram_bridge.py` / `telegram_daemon.py` | Standalone Telegram poller (+ heartbeat when run directly) | Not needed any more: `core_service` starts the poller itself. |
| `overnight_autonomous_pipeline.py`, `repo_trainer.py`, `self_distillation.py`, `simulate_training.py`, `daily_qa_generator.py` | Batch jobs, run by hand | All drive a real `ZaineAgent` and write into memory. |

### Processes and threads (seminar path)
- **core_service process**:
  - `ZaineCoreServer` (one thread per HTTP request)
  - `ZaineModelPrewarm`
  - `ZaineTelegramBridge` (✅ new; one thread per Telegram update; logs to `data/telegram_bridge.log`)
  - 4-worker tool pool (only used for multi-tool turns)
- **TUI process**: Textual event loop plus the telemetry thread (every 2s: psutil, `nvidia-smi`, vault stats).
- **Heartbeat** (reminders, briefings, desk camera, YouTube scheduler) runs **only** under `main.py` / `telegram_bridge.py __main__`.

### Request lifecycle (`POST /api/chat/stream`)
1. **Check the request:** Host check, then `X-Zaine-Token` check (the token is written to `.zaine_core.json` on each start).
2. **Queue:** `coordinator.claim_request` lets one request run at a time (FIFO); results are cached for 300s.
3. **Stream setup:** SSE `queued` → `warming` (if the model is still loading) → `running`.
4. **Agent turn:** `agent.chat_stream`:
   - add the user turn to memory;
   - natural-language persona triggers;
   - biometric shortcut;
   - `router.classify_task_tier`;
   - `classify_intent_clusters` → `build_clustered_system_prompt` (+ ~2,000 chars of memory);
   - up to 6 Ollama ↔ tool hops.
5. **Tool call:** `_execute_tool` maps aliases → normalizes params → guest-role gate → `TOOL_REGISTRY[name](**args)`.
6. **Approval (if the tool needs it):**
   - `approval.require_approval` saves a proposal (`data/zaine_approvals.db`), sends SSE `approval_required` and posts the Telegram card;
   - `wait_for_decision` re-reads the DB every 1.5s (heartbeat every 5s, 180s limit; ✅ now marked EXPIRED/CANCELLED when it gives up);
   - a decision arrives via the TUI (`/api/approval/respond`) or Telegram (`handle_callback_query`) → `ApprovalRegistry.approve/deny` (✅ now only acts on PENDING rows).
7. **Finish:** stream `token` events, then `done`.

---

## 2. File index by subsystem

### Core runtime
| File | Role |
| :--- | :--- |
| `core_service.py` | HTTP+SSE daemon on 127.0.0.1:7860–7869. Endpoints: `/api/health`, `/api/status`, `/api/chat`, `/api/chat/stream`, `/api/approval/respond`, `/api/chat/cancel`, `/api/mode`, `/api/voice/*`, `/api/history`, `/api/context/clear`. Also pre-warm and the Telegram poller. |
| `coordinator.py` | Global request serializer plus idempotency cache. |
| `core_router.py` | Model names (`zaine-reflex-7b`, `zaine-fast-3b`, `zaine-coder-7b`, `moondream`), fallback chains, tier keywords, parallel tool pool. |
| `agent.py` | `ZaineAgent`: intent detectors, tool-call parser, ~200 tool aliases, guest gate, the chat loop. |
| `approval.py` | Proposals DB, Telegram approval card, wait loop, `require_approval`. |
| `zaine_env.py` | ✅ new: `running_under_tests()` (replaces the unreliable `"unittest" in sys.modules` check). **Must be committed.** |
| `ollama_profiler.py` | Logs every Ollama call (prints to the console). |
| `thermal_guard.py` | ACPI temperature via PowerShell, cool-down waits, `clean_unwanted_files`. |
| `main.py`, `heartbeat.py` | Legacy launcher; 15s proactive daemon (reminders, battery, briefings, ergonomics, desk presence, YouTube schedule). |

### Tools (119 registered)
| File | Role |
| :--- | :--- |
| `tools.py` | `TOOL_REGISTRY` plus most tool functions: workspace files, run script, shell, apps, media, web, vault, YouTube wrappers, toggles. |
| `tool_clusters.py` | 5 clusters (SYSTEM, DEV_CODE, MEDIA_STUDIO, WEB_SOCIAL, VAULT_MEMORY). Picks ≤2 clusters per message by keyword and builds the system prompt. Clusters only shape the prompt; any registered tool can still be executed. |
| `toolmaker.py`, `custom_tools/` | The model writes and hot-registers new tools; also `pip install`. Custom: `code_benchmarker`, `system_diagnostics`, `instagram_manager`. `IronHands/` is an unrelated cloned repo. |
| `public_apis.py`, `browser_agent.py`, `social_omni.py`, `email_client.py` | Keyless APIs, scraping/downloads, social URLs and Unstop, Gmail IMAP/SMTP. |
| `code_reviewer.py`, `ponytail.py`, `hive_mind.py`, `zaine_cascade.py`, `total_recall.py`, `home_ops.py` | Lint, "7-rung" coder prompt, keyword sub-agents, VS Code companion, activity journal (no writer → dead), DB backup/health. |

### Memory & knowledge
| File | Role |
| :--- | :--- |
| `memory.py` | `zaine_tasks.db` (`memories`, `task_learnings`, `conversation_episodes`), `ConversationMemory` (24-message window), per-turn context builder, reflection and episode summaries (off by default). |
| `memory_manager.py`, `memory_types.py`, `obsidian_adapter.py` | Trust policy and injection regexes; `MemoryEntry` YAML; Obsidian vault storage and the per-turn full-scan search. |
| `vault.py`, `knowledge_engine.py` | `vault/vault.db` FTS5 second brain; `data/knowledge_vault.db` FTS5 developer knowledge. |
| `idea_engine.py`, `ai_daily_intel.py`, `morning_briefing.py`, `daily_qa_generator.py`, `migrate_memory_sqlite_to_obsidian.py` | Ideas, daily "AI news", briefing, nightly QA generation, one-shot migration. |

**Source of truth:** facts → `memories`; lessons → `task_learnings` (vault `05_Lessons` holds copies); user notes → vault files; trust and provenance exist **only** in vault frontmatter.

### UI
| File | Role |
| :--- | :--- |
| `zaine_tui.py`, `tui/app.py`, `tui/client.py` | Entry point, boots/waits for the core; Textual app (chat, HUD on F2, topology on F3, slash commands, approval handling); httpx SSE client with timeouts (first token 60s, idle 20s, 300s ceiling). |
| `tui/widgets/*` | Header, footer, HUD, chat cards and **ApprovalCard**, reasoning block, tool line, input, banner, 3D graph. |
| `tui/views/topology_view.py` | ✅ rebuilt: F3 graph workspace. `[1]` live execution DAG, `[2]` system topology, `[3]` 3D orbit; turn summary, system status and event stream cards (all real data). |
| `tui/exec_graph.py`, `tui/system_graph.py`, `tui/widgets/digraph.py` | ✅ new: execution digraph model folded from SSE events (route, profiler, tool start/done, approvals); real system topology (core `/api/status`, Ollama `/api/tags` and `/api/ps`, tool clusters, vault folders, Telegram lock port); layered digraph renderer and HUD trace. |
| `tui/telemetry.py`, `tui/theme.py` | psutil/`nvidia-smi` telemetry and sparklines (tool count now read from `tool_clusters`, not by importing `tools.py`); colours. |
| `terminal.py`, `terminal_ui.py` | Legacy Rich CLI (broken against the current core, see above). |

### Telegram, voice, perception
| File | Role |
| :--- | :--- |
| `telegram_bridge.py`, `telegram_daemon.py` | Bot: whitelist/pairing, ~25 commands, approval and YouTube callbacks, voice notes (faster-whisper), photos (Moondream), alert/photo/video helpers. |
| `voice.py`, `voice_synthesizer.py`, `wakeword.py` | STT with energy end-pointing; TTS Edge → Piper; barge-in; Jarvis TTS facade (mostly dead); wake word (dead). |
| `vision.py`, `camera_stream.py`, `face_id.py`, `gesture_control.py` | Screen/webcam → Moondream; shared camera singleton; YuNet+SFace face-ID and admin/guest roles; MediaPipe gestures. |
| `gemini_validator.py` | Cloud QA validation for the nightly generator. |

### YouTube studio (`youtube_studio/`, `overnight_autonomous_pipeline.py`)
- `scheduler.py` runs 6 daily slots, then a render, then the `data/pending_review/` queue, then a Telegram video with Approve/Reject.
- On approval, `uploader.py` publishes to YouTube.
- Rendering: `content_generator.py` (non-anime; PIL frames + edge-tts + Whisper) and `anime_editor.py` + `fx_engine.py` (anime; ffmpeg).
- Overnight loop: intel, AST scan, DB vacuum, ideas, editing "learning", pruning.

### Training, tests, config
- `finetune/`, `repo_trainer.py`, `self_distillation.py`, `simulate_training.py`, `merge_adapter.py`, `model_activations_probe.py`: none of this is used at runtime. The deployed models are base Qwen + Modelfiles.
- `Modelfile.reflex7b` and `Modelfile.coder7b` are live; `Modelfile` and `Modelfile.coder` are dead. `zaine-fast-3b` has no Modelfile in git; its recipe is only in the gitignored `scratch_audit/Modelfile.zaine-fast-3b`.
- Tests: 109 unittest cases across 8 root files. `tests/` has no `__init__.py` and holds scripts, not TestCases. `test_mic.py` blocks discovery.

---

## 3. Data stores
| Store | Contents (counts on 2026-10-22) |
| :--- | :--- |
| `zaine_tasks.db` | memories 18 · task_learnings 853 (**439 distinct**; 270 rows are 10 repeated "AI intel" texts) · conversation_episodes 9 · tasks 13 · reminders 1 · enrolled_faces 2 · telegram_chat_settings 2 |
| `data/zaine_approvals.db` | 193 proposals (~120 look test-generated) |
| `vault/vault.db` | notes 43 rows over 22 files (duplicates) + `notes_fts` |
| `data/knowledge_vault.db`, `data/zaine_ideas.db` | 37 FTS rows · 9 ideas |
| `zaine_memory.db` | empty orphan |
| `.zaine_core.json` | port, pid, **auth token** (written on every core start; tests overwrite it) |

---

## 4. Ranked findings

### Fixed today
- ✅ Telegram taps were never received on the TUI/demo path, because no poller ran. `core_service` now starts the poller.
- ✅ The poller died for the whole process after one failed `getMe` (e.g. booting before Wi-Fi). It now retries with backoff.
- ✅ The polling loop busy-spun on Telegram errors. It now waits 5s after a failure.
- ✅ Timed-out approvals stayed PENDING, so late taps said "APPROVED" while nothing ran. They are now marked EXPIRED/CANCELLED.
- ✅ Approve/deny race: they now update only PENDING rows, so the first decision wins and the phone shows the real result.
- ✅ The Telegram bridge forwarded chats without `X-Zaine-Token`, so every forwarded chat got 401.
- ✅ Bare "approve…" or "deny…" text acted on the newest proposal. Telegram now requires `/approve <id>` / `/deny <id>`.
- ✅ TUI approval card showed approving as "DENIED", and denied or expired actions as "APPROVED". It now shows the real outcome.
- ✅ TUI approval card hid text and could crash: `[Environment]::…` lost characters and `[/]` raised `MarkupError`. It now renders literally.
- ✅ Typing `y`/`n` with no pending card cancelled the running stream. That is now ignored.
- ✅ The TUI header stuck at "WARMING UP" because `tui/app.py` was missing `import json`.
- ✅ The unreliable test detection disabled the telemetry/readiness loop and would have disabled the Telegram poller. All 10 call sites now use `zaine_env.running_under_tests()`.
- ✅ The approval tests wrote into the real approvals DB and sent cards to your phone. They now use a temp DB and a stub.
- ✅ `num_ctx` mismatch forced ~12.4s model reloads on code requests.
- ✅ Also fixed: `zaine_tui.py` indentation and missing `import os`; Ponytail `user_content`; the `.bat` readiness wait.

### 🔴 Critical (open)
1. **Coordinator wedges after a client disconnect** (`core_service.py` ~1112–1168). If the TUI closes or is killed while queued or warming, the request stays "running" forever. Every later request then times out after 120s until restart. *This is another way to get a "stuck" Zaine.*
2. **Double YouTube publish.** Each Telegram tap runs in its own thread, and the "already published" guard never matches (`uploader.py` ~227–250, ~395–438).
3. **`create_custom_tool` approval fails open** (`toolmaker.py` ~192). If proposal creation raises, the model-written code is written, imported and registered anyway. Custom tools can also overwrite built-ins (`execute_command`, `send_email`) and are reloaded on every boot.
4. **Unapproved external actions:**
   - `send_email` (the model picks the recipient);
   - `upload_youtube_video` / `generate_youtube_short(upload_now=True)` / `generate_manga_recap(upload_now=True)` (public uploads with no review);
   - `install_python_package`;
   - Instagram reel publish.

### 🟠 High (open)
**Core / agent**
5. A cancelled request keeps running alongside the next one: two `_chat_stream_impl` calls on one agent, interleaved memory, two generations on the GPU (`coordinator.py` ~209).
6. The biometric shortcut fires on normal questions ("look at memory usage", "who am i talking to") and opens the webcam. An "unknown" result then locks write tools for the whole session (`agent.py` ~132–139, 1018–1045).
7. Hitting the 6-hop tool limit returns an empty reply (`agent.py` ~1111–1351).
8. `ZAINE_DEMO` caps output at 300 tokens. That truncates `write_workspace_file` JSON, and the parser still writes the truncated file (`agent.py` ~1112, 440–458).
9. The core prints `[OLLAMA_CALL]` lines into the console the TUI draws on (`ollama_profiler.py` ~71; the `.bat` files use `-NoNewWindow`).
10. In fast mode, any Ollama error falls back to the 7B model, which evicts the 3B mid-demo (`agent.py` ~1132–1138).

**UI**
11. `terminal_ui.py` sends no auth token, so `main.py` / `run_zaine.bat` chat is broken (401).
12. `FooterBar.render` runs `nvidia-smi` on every re-render, which stalls the TUI mid-stream (`tui/widgets/footer.py` ~66).
13. A queued request gets no keep-alive pings for up to 120s, so the client times out. Its cancel then **denies every pending approval globally**, including other clients' (`core_service.py` ~981).
14. Ctrl+C neither cancels nor quits, because the input box captures it. Esc-cancel races with the next turn and shows two "interrupted" cards.

**Telegram / perception**
15. `telegram_daemon.py` restarts with no delay. Since the lock is never released, every restart fails instantly in a tight loop.
16. Face-ID fails open:
    - the default role is admin;
    - the session timeout is a no-op;
    - `/enroll` over Telegram can enrol an admin from whoever is at the camera, with no liveness check.
17. The Gemini API key is passed in the URL, so it leaks into exception text and logs (`gemini_validator.py` ~107, 147; `youtube_studio/analytics.py` ~68).
18. Barge-in listens to the microphone while Zaine speaks through the speakers, and its keywords include "zaine", "wait" and "stop". In a hall, Zaine can cut itself off. Use headphones or turn barge-in off for the demo.

**Tools / security**
19. `start_local_server` binds **all interfaces**, so the workspace is browsable on venue Wi-Fi. `stop_local_server` pastes `port` into a PowerShell string (injection) and always kills whatever is on :8000.
20. `query_public_api` and `browse_web` can GET any URL, including `127.0.0.1:7860` (the core) and `:11434` (Ollama): SSRF and an exfiltration path. `browse_web` is also guest-allowed.
21. `code_benchmarker` runs any `.py` on disk without approval. `run_python_script`'s project-root fallback is also open.
22. `system_diagnostics kill_process` matches process names by substring, so "python" kills Zaine and Ollama.
23. The `execute_command` blacklist is cosmetic (`Stop-Computer`, `rd /s /q`, `powershell -enc` all pass). Only `cwd` is set, so `cd ..` and absolute paths work.
24. `check_emails` fetches with RFC822, which marks unread mail as read, and the heartbeat calls it unattended.
25. `close_application` with an unknown name presses Alt+F4 on whatever window has focus, likely the TUI.
26. `upload_youtube_video_tool` checks lowercase statuses, so every outcome is reported as "Upload error: None".

**Memory**
27. "Live AI news" is fake: the web result is discarded and 10 hard-coded 2025 items are stamped with today's date. Each refresh re-adds 10 lessons, 10 vault notes and 1 vault row; this is where most of the lesson flood comes from (`ai_daily_intel.py` ~110–178).
28. Each `save_memory` creates a new vault note, so updated facts leave stale duplicates that are retrieved equally (`memory.py` ~115, `memory_manager.py` ~229).
29. The user profile (1,646 chars) sits inside the leftover budget, so it is truncated or dropped whenever vault hits exceed ~350 chars (`memory_manager.py` ~469–479).

**YouTube**
30. Months-old pending items mark morning slots 1–3 as "completed" every day, so those slots never run (`scheduler.py` ~493–497).
31. `anime_editor.py` uses `json` without importing it. History files are truncated to 0 bytes, and clip and track deduplication never work.
32. Failed uploads are still marked approved and completed, the pending item is deleted, and Telegram says "PUBLISHED LIVE".
33. A failing render is retried by the heartbeat every 15s all day, including a fresh 180s yt-dlp download each time.
34. Renders have no demo or user-active guard. They run inside the heartbeat thread, so reminders and battery checks stall during a render.
35. **Copyright/ToS exposure:** it downloads the top YouTube search result with yt-dlp and re-uploads anime footage and OSTs to a public channel.

**Repo / tests**
36. Tests overwrite the real `.zaine_core.json` and pre-warm a real Ollama model with `keep_alive -1` (`CoreService.start_server` in test_approval b/c and test_cli 17). Running tests can repoint a live TUI or bridge.
37. `zaine_env.py`, `ollama_profiler.py`, the demo `.bat` files and `demo_workspace/` are untracked, so a fresh clone crashes when CoreService starts.
38. Personal data is tracked in git:
    - vault profile notes;
    - activity journal;
    - briefings;
    - conversation logs;
    - `data/pending_review/*.json` with absolute paths.

    Check whether the GitHub remote is public.

### 🟡 Medium (selected)
**Core / agent**
- Parallel tool calls lose the approval and cancel context, so no TUI card appears and only Telegram can approve.
- Natural-language persona triggers fire on substrings: "what is ultron mode?" switches to Ultron.
- Tool JSON anywhere in a reply is executed.
- The parser rewrites `, }` inside file content and mangles non-ASCII text.
- `" ".join` adds a leading space to every code line in stored and Telegram replies.
- Each `/api/status` call can spawn PowerShell for the temperature (no cache on failure).
- The heartbeat's desk-presence check uses the camera and Moondream every 15s after 30 idle minutes, and "idle" counts only Telegram activity.

**Telegram**
- The typing indicator can run forever when two messages overlap.
- `explain…` text is hijacked by the `/explain` handler.
- The lock message echoes the pair PIN, and the default PIN is 7788.
- Telegram cards show a 60-char title, not the full command, and the Markdown is unescaped.

**Camera / voice**
- `camera_stream` serves a stale frame as "live" and can reopen the camera after `stop()`.
- A missing `edge_tts` or `av` package disables `io`/`wave` and breaks the offline Piper fallback.

**Memory**
- Per-turn full vault scan with YAML parsing; a 5s cap silently drops `05_Lessons`.
- Non-atomic note writes (unlink + rename).
- `vault.add_to_vault` adds duplicate DB rows.
- `idea_engine` selects the nonexistent `task_learnings.lesson` column.

**YouTube**
- The overnight loop exits immediately if started before midnight.
- Single-clip anime renders have no duration cap.
- The "climax" analysis is a hard-coded `[14.2, 22.8, 31.5]`.
- Higgsfield credits are spent and the output is discarded.
- Disk usage grows without limit (`raw_clips` is 840 MB).

### ⚪ Low / dead code
- **Dead modules and tools:** `wakeword.py`; most of `voice_synthesizer.py`; the `gesture_control` HUD logic; `recall_activity` (no writer); the `zaine_cascade` thin client.
- **Dead functions:** `vault.sync_vault_files`; `memory_manager.update/retrieve/create_candidate`; several YouTube helpers.
- **Dead training files:** `merge_adapter.py`, `Modelfile`, `Modelfile.coder`, `merged_model/`, the fine-tune deploy steps.
- **Stale docs:** README model table and env var name (`ZAINE_OBSIDIAN_VAULT_PATH`); an unclosed code fence; `ZAINE_CURRENT_STATE.md`, `ZAINE_PRODUCTION_SPECIFICATION.md` and the migration docs still describe `ui.py`/Electron/3B/deepseek.
- **Missing from `requirements.txt`:** httpx, PyYAML, beautifulsoup4, imageio-ffmpeg, mediapipe, pygame, google-auth-oauthlib, rembg, scenedetect, yt-dlp, instagrapi.
- **Tests:** `test_mic.py` blocks test discovery and should be renamed.
- **Secret-scanner bait:** the fake `sk_live_…` string in `repo_trainer.py:73` and the tracked jsonl.

---

## 5. Readiness plan (3 weeks)

| Week | Focus | Items |
| :--- | :--- | :--- |
| 1 | Demo path never gets stuck or lies | 1, 5, 6, 7, 8, 9, 10, 12, 13, 14, 18, 34 (no renders while a user session or `ZAINE_DEMO` is active), 36, 37; live phone approval test |
| 2 | Gate every external or destructive action | 3, 4, 15–17, 19–26, plus fail-closed approval for toolmaker; the security wall from `ZAINE_POST_SEMINAR_SPEC.md` §2.4–2.9 |
| 3 | Data hygiene, YouTube correctness, docs, rehearsal | 2, 27–33, 35, 38, dedupe lessons (after backup), requirements, README/docs refresh, dry runs |
