# ZAINE: System Recovery & Evolution Blueprint
## Technical Debt Analysis & Remediation Roadmap

This document outlines the strategic path to transition Zaine from a collection of scripts to a professional autonomous agent system.

---

## 🚩 The Core Problems (The "Why")

### 1. State Fragmentation ("Split-Brain")
Zaine's brain is currently split. `memory.py` (the active agent) writes to `zaine_tasks.db`, but the `home_ops.py` watchdog (the system's safety net) monitors a stale file called `zaine_memory.db`. 
**Result**: The system is backing up a ghost while the real brain is unmonitored.

### 2. Tool Blindness
There are 119 tools in the `TOOL_REGISTRY`, but only 69 are clustered. Because the LLM prompt is built strictly from clusters, **50 tools are functionally invisible**.
**Result**: Zaine is 42% less capable than its code suggests.

### 3. Session Volatility
Zaine has no concept of "Threads." It's one linear stream of messages. If you restart the app or switch from Desktop to Telegram, the context is gone.
**Result**: No persistence. No "New Chat" capability.

### 4. Hardware Ceiling (The VRAM Wall)
With only 4GB of VRAM, loading `deepseek-r1:7b` (4.7GB) forces the system into "swap" (paging to system RAM).
**Result**: Token speed drops from ~38 t/s to < 3 t/s, causing the UI to feel frozen.

---

## 🛠 The Solution: Three-Phase Remediation

### Phase 1: The "Quick Wins" (Immediate Stabilization)
*Goal: Stop the bleeding and unlock existing power. Estimated time: 2-4 hours.*

**Fix A: Unify the Brain**
- **Action**: Update `home_ops.py` and all backup scripts to target `zaine_tasks.db`.
- **Logic**: Ensure the `digital_sentinel` is monitoring the actual active database.

**Fix B: Illuminate the Tools**
- **Action**: Map the 50 orphaned tools into `tool_clusters.py`.
- **Logic**: This requires no new code, only configuration. It instantly restores the missing 42% of capabilities.

**Fix C: Camera Mutex Lock**
- **Action**: Implement a `threading.Lock()` in `camera_stream.py`.
- **Logic**: Force `Face-ID`, `Vision`, and `Gesture` modules to queue their requests for the camera rather than crashing the DirectShow driver.

---

### Phase 2: The Architectural Shift (The Core Redesign)
*Goal: Solve the memory and session limitation. Estimated time: 1-2 weeks.*

**Fix D: Session-Based Persistence**
- **Action**: Create a `chat_sessions` and `messages` table in SQLite.
- **Logic**: Transition from `self.history = []` to `session_id` based loading. This enables a "Chat History" sidebar in the HUD.

**Fix E: Dynamic Context Management**
- **Action**: Replace the 12-turn FIFO limit with a weighted context filler.
- **Logic**: Utilize the full 32k token window. Priority: `Active Thread` $	o$ `User Profile` $	o$ `Semantic Memories`.

**Fix F: Semantic Vector Retrieval**
- **Action**: Integrate a lightweight local vector store (FAISS).
- **Logic**: Replace `LIKE %word%` SQL queries with embedding-based search. Zaine will find memories by *meaning*, not just keywords.

---

### Phase 3: Intelligence & VRAM Optimization
*Goal: Maximize the 4GB VRAM and improve reasoning. Estimated time: Ongoing.*

**Fix G: Neural Intent Routing**
- **Action**: Replace rigid substring checks in `core_router.py` with a "Routing Prompt."
- **Logic**: Ask the 3B model to categorize the intent into a Tier (Reflex, Deep, Coder) before the main loop starts.

**Fix H: VRAM Orchestrator**
- **Action**: Implement an explicit `unload_model()` call before loading heavy reasoning models.
- **Logic**: Prevent "VRAM spill" into system RAM by ensuring only one large model is resident at a time.

**Fix I: True IDE Integration**
- **Action**: Move `zaine_cascade` from a terminal wrapper to an LSP (Language Server Protocol) client.
- **Logic**: Give Zaine the ability to parse the actual AST (Abstract Syntax Tree) of the project for true autonomous coding.

---

## 📉 Hardware Boundary Reference
| Resource | Limit | Status | Constraint |
| :--- | :--- | :--- | :--- |
| **VRAM** | 4.0 GB | **Critical** | Only 1.3GB headroom after Reflex Core. |
| **System RAM** | 15.6 GB | **High** | Spikes to 95% during video rendering. |
| **CPU** | i5-13420H | **Stable** | Efficient for STT/TTS; bottlenecked during offloading. |
