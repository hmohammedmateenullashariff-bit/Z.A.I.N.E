# ZAINE CURRENT STATE: Architectural Map (Audit: 2026-09-17)

This document is a ground-truth architectural reference for Zaine. It is designed to be the primary source of truth for a full system redesign.

================================================================
SECTION 1 — Core Agent Loop
================================================================

### 1. Message Flow Trace (Input -> Output)

1.  **Input Ingestion**:
    *   **Voice (Desktop)**: `wakeword.py` (Wake-phrase) -> `voice.py` (STT) -> Raw Text.
    *   **Text (Desktop)**: `ui.py` (HTTP POST `/api/chat`) -> Raw Text.
    *   **Text (Mobile)**: `telegram_bridge.py` (Long-polling) -> Raw Text.
2.  **Routing & Classification (`core_router.py`)**:
    *   Input is passed to `classify_task_tier()`.
    *   **Reflex (Default)**: $\to$ `qwen2.5:3b`.
    *   **Deep Reasoning**: (Matches "explain in detail", etc.) $\to$ `deepseek-r1:7b`.
    *   **Coder**: (Matches "architect", "refactor", etc.) $\to$ `qwen2.5-coder:3b`.
    *   **Vision**: (Matches "see screen", etc.) $\to$ `qwen2.5:3b` (via vision tools).
3.  **Context Assembly (`memory.py` & `tool_clusters.py`)**:
    *   **Memory**: Retrieves user profile (`user_profile.md`), KV facts (`memories` table), and behavioral lessons (`task_learnings` table) via keyword matching.
    *   **Tools**: `tool_clusters.py` selects the top 2 relevant clusters (e.g., `SYSTEM`, `DEV_CODE`) and injects only those tool schemas into the prompt to save context.
4.  **Inference (Ollama)**:
    *   Payload dispatched to Ollama `/api/chat`.
    *   **Reflex Core** (`qwen2.5:3b`) is pinned in VRAM (`keep_alive: -1`) for <800ms latency.
5.  **Tool Execution Loop (`agent.py` -> `tools.py`)**:
    *   If LLM outputs a tool call $\to$ `agent.py` validates permissions (Admin vs Guest) $\to$ executes function in `tools.py` $\to$ feeds result back to LLM.
    *   Maximum hops: 6.
6.  **Output Dispatch**:
    *   **Voice**: Text $\to$ `voice_synthesizer.py` (Edge-TTS / Piper) $\to$ PyAudio.
    *   **HUD**: Text/Telemetry $\to$ `ui.py` (SSE Stream) $\to$ `hud.js` (Electron).
    *   **Telegram**: Text/Voice $\to$ `telegram_bridge.py` $\to$ Telegram Bot API.

### 2. Model Inventory & Actual Usage
| Model | Purpose | Invocation | Frequency | Status |
| :--- | :--- | :--- | :--- | :--- |
| **`qwen2.5:3b`** | Core Reflex / Tool Caller | `core_router` | **> 98%** | **The Workhorse.** Pinned in VRAM. |
| **`deepseek-r1:7b`**| Deep Reasoning (CoT) | `core_router` | **< 0.5%** | **Dormant/Fragile.** Forces CPU offload (VRAM > 4GB). |
| **`qwen2.5-coder:3b`**| Specialized Coding | `core_router` | **~ 1.5%** | **Underutilized.** Only triggered by exact phrases. |
| **`moondream`** | Vision / OCR | `vision.py` | On-Demand | **Solid.** Fast, but causes brief VRAM paging. |
| **`nomic-embed-text`**| Vector Embeddings | `daily_qa_generator`| Nightly | **Narrowly Scoped.** CPU-only. |
| **`YuNet/SFace`** | Face-ID | `face_id.py` | On-Demand | **Solid.** CPU-based ONNX. |
| **`MediaPipe`** | Gesture Control | `gesture_control.py` | Continuous | **Fragile.** High CPU overhead. |

### 3. Tool Registry & Clusters
*   **Total Tools**: 119 in `TOOL_REGISTRY`.
*   **Clustered Tools**: 69 mapped across 5 clusters (`SYSTEM`, `DEV_CODE`, `MEDIA_STUDIO`, `WEB_SOCIAL`, `VAULT_MEMORY`).
*   **Orphaned Tools**: **50 tools** are registered but **not clustered**. They are functionally invisible to the LLM because their schemas are never injected into the prompt.
*   **Validation**: The internal `_validate_tool_registrations` check is unidirectional (checks if cluster tools exist in registry, but not vice versa).

================================================================
SECTION 2 — Data & State Architecture
================================================================

### 4. SQLite Database Map
| Database | Table | Row Count | Purpose | Owner |
| :--- | :--- | :--- | :--- | :--- |
| `zaine_tasks.db` | `tasks` | 13 | To-do list & Priority | `tools.py` |
| | `memories` | 17 | User preferences/facts | `memory.py` |
| | `task_learnings` | 831 | Behavioral lessons | `memory.py` |
| | `reminders` | 1 | Scheduled alerts | `heartbeat.py` |
| | `conversation_episodes`| 9 | Summarized session logs | `memory.py` |
| | `enrolled_faces` | 2 | Biometric embeddings | `face_id.py` |
| `zaine_approvals.db`| `proposals` | 24 | Guardian approval queue | `approval.py` |
| `zaine_ideas.db` | `zaine_ideas` | 9 | Brainstorming vault | `idea_engine.py` |
| `knowledge_vault.db`| `knowledge_fts`| 37 | Technical FTS index | `knowledge_engine.py` |
| `vault.db` | `notes` | 41 | Second Brain notes | `vault.py` |
| `zaine_memory.db` | `task_learnings`| 100 | **STALE.** Legacy mirror. | `home_ops.py` |

**Critical Finding**: "Split-Brain" state. `memory.py` uses `zaine_tasks.db`, but `home_ops.py` monitors/backs up the stale `zaine_memory.db`.

### 5. JSON State Inventory
*   **YouTube Pipeline**: `youtube_schedule_state.json`, `youtube_queue.json`, `youtube_token.json` (Schedules & Auth).
*   **Intel**: `daily_ai_intel.json`, `anime_editing_intelligence.json`, `editing_knowledge.json`.
*   **Curriculum**: `data/knowledge_vault/*.json` (Technical blueprints).
*   **Approvals**: `data/pending_review/*.json` (Content for review).
*   **Training**: `repo_training_status.json`, `distillation_checkpoint.json`.

### 6. Memory Architecture
*   **Working Memory**: FIFO sliding window (capped at 12 turns / 24 messages).
*   **Episodic Memory**: Summarized "episodes" stored in `zaine_tasks.db`. Triggered only on window overflow.
*   **Behavioral Memory**: `task_learnings` store "If X, then Y" lessons.
*   **Context Waste**: Model supports 32k tokens; Zaine uses < 5% (~1.5k tokens). Long debugging threads are truncated prematurely.

================================================================
SECTION 3 — Application/UI Layer
================================================================

### 7. UI Stack
*   **Backend**: `ui.py` (Python `ThreadingHTTPServer` on port 7860).
*   **Frontend**: Electron (`main.js`) $\to$ HTML/CSS/JS.
*   **Surfaces**:
    *   **Main HUD**: Telemetry matrix, Arc Reactor canvas, Chat stream.
    *   **Lock Screen**: Biometric verification overlay.
    *   **File Browser**: Sliding holographic panel for `workspace/`.
    *   **Gesture Toast**: OSD for hand gesture feedback.
*   **Modes**: `JARVIS` (Default/Cyan), `ULTRON` (Red/Unchained), `GUEST` (Purple/Restricted).

### 8. Entry Points
*   **`main.py`**: Desktop voice/console (Primary).
*   **`telegram_bridge.py`**: Mobile gateway.
*   **`launch_hud.py`**: Headless HUD server.
*   **State Isolation**: `main.py` and `telegram_bridge.py` run in separate processes. They share SQLite DBs but have **separate in-memory conversation histories**.

### 9. Conversation History Assessment
**Assessment**: **NO multi-thread support.**
Zaine has one linear session per process. There are no `session_id`s or `thread_id`s. Implementing "New Chat" requires a complete database migration to a `messages` table and a frontend sidebar.

================================================================
SECTION 4 — Capability Inventory
================================================================

### 10. Working Status
| Subsystem | Status | Note |
| :--- | :--- | :--- |
| **Face-ID / Permissions** | Fully Working | Fast CPU inference; reliable tier enforcement. |
| **Telegram Voice** | Fully Working | High-quality OGG notes; auto-chunking logic. |
| **Electron Shell** | Fully Working | Stable acrylic wrapper. |
| **YouTube Pipeline** | Partially Working | Rendering works; publishing is fragile/manual. |
| **Episodic Memory** | Partially Working | Summarization works; retrieval is crude SQL `LIKE`. |
| **Gesture Control** | Built but Fragile | High CPU load; hardware contention with Camera. |
| **Nightly QA** | Documented / Fragile | Infrastructure exists; evolution is not automated. |
| **`zaine_cascade.py`** | Documented / Fragile | Not a true IDE agent; just a terminal wrapper. |

### 11. Orphaned/Dead Code
*   `merged_model/`: Stale merge artifacts.
*   `finetune/checkpoints`: Old QLoRA weights.
*   `scratch/`: Numerous one-off test scripts.
*   `hive_mind.py` / `total_recall.py`: Registered in `tools.py` but omitted from clusters (LLM cannot see them).

================================================================
SECTION 5 — Known Technical Debt & Constraints
================================================================

### 12. Resource Constraints
*   **VRAM (4GB RTX 2050)**: 
    *   $\sim$2.7 GB locked (`qwen2.5:3b` + Windows DWM).
    *   Loading `deepseek-r1:7b` (4.7GB) or `moondream` (1.7GB) causes system RAM spill and severe latency.
*   **System RAM (15.6GB)**: High utilization (>90%) during video rendering or model switching.
*   **CPU (i5-13420H)**: Solid for STT/TTS, but struggles during heavy LLM offloading.

### 13. Unresolved Fragilities
1.  **Split-Brain DB**: `home_ops.py` backs up the wrong memory file.
2.  **Invisible Tools**: 50 tools are registered but unclustered.
3.  **No Session IDs**: No way to switch between distinct chat threads.
4.  **Camera Lock**: Multiple modules fight for Camera Index 0, causing crashes.
5.  **Keyword Routing**: `core_router.py` is too rigid; misses complex reasoning requests.
6.  **Search Quality**: Memory retrieval uses `LIKE %word%` instead of semantic vectors.
7.  **IDE Illusion**: `zaine_cascade` lacks actual AST/editor integration.
