# Z.A.I.N.E — Terminal-First UX Transformation Implementation Plan

## 1. Architectural Analysis & Findings
- **Core Architecture**: Phase 2a unified core process (`ui.py` running `ThreadingHTTPServer` on port 7860/7875 discovered via `.zaine_core.json`). Single `ZaineAgent` instance coordinated by `RequestCoordinator` with atomic idempotency and FIFO queueing.
- **Current Terminal**:
  - `main.py` runs a basic `text_loop()` with raw `input()` and print statements.
  - `zaine_cascade.py` provides coding tools (`/code`, `/inspect`, `/run`, `/test`, `/files`) and connects to `POST /api/chat/stream` via SSE.
- **Capabilities Discovery**: `get_active_capabilities()` in `tools.py` dynamically introspects `TOOL_REGISTRY` (119 tools) and `TOOL_CLUSTERS`.
- **Session/History**: `conversation_episodes` table in `zaine_tasks.db` stores past episodic summaries; `POST /api/context/clear` resets in-memory FIFO conversation history.
- **Dependencies**: `rich` (Console, Panel, Table, Live, Text, Markdown, Syntax) is installed and operational.

## 2. Design & Visual Identity System
- **Tone**: Technical, intelligent, premium, restrained (Claude Code x Hermes UX x Z.A.I.N.E Identity).
- **Color Palettes**:
  - **Jarvis Protocol (Default)**: Cyan (`#00e5ff`), Electric Blue (`#2979ff`), Pure White (`#ffffff`), Slate/Dim (`#78909c`).
  - **Ultron Protocol**: Crimson (`#ff1744`), Blood Amber (`#ff9100`), Steel Gray (`#b0bec5`).
  - **Status Accents**: Green (`#00e676` for success/ready), Yellow (`#ffd600` for tools/queued), Red (`#ff5252` for errors).
- **Borders & Glyphs**:
  - Rounded Unicode box drawing (`╭─╮╰─╯`), with automatic ASCII fallback (`+-+|`) on restricted consoles.
  - Meaningful status glyphs: `●` (ready), `⟳` (active/spinning), `✓` (success), `✗` (failure), `▸` / `▼` (collapsed/expanded).

## 3. Component Breakdown

### A. Terminal Renderer Module (`terminal_ui.py`)
1. **Startup Capability Panel**:
   - Dynamic introspection via `get_active_capabilities()` and core status endpoints.
   - Displays Brain tiers, registered tools count, active personas, memory backend, Telegram bridge status, active user identity, and mode.
2. **Top Status Bar**:
   - Compact line: `Z.A.I.N.E │ JARVIS │ qwen2.5:3b │ COMPANION │ ● READY │ 0.8s`
   - Real-time state transitions: `READY`, `QUEUED (#1)`, `THINKING`, `TOOL: <name>`, `STREAMING`, `ERROR`.
   - Timer displaying operation duration.
3. **Structured Reasoning Display**:
   - Collapsible thinking/planning section (`▸ Reasoning · 1.4s` vs `▼ Reasoning`).
   - Surfaces intentional reasoning/planning events.
4. **Tool Execution Engine**:
   - Compact status lines with execution timings: `✓ search_files  project-z · 1.2s`.
   - Tool output collapsing: collapsed one-liner by default, expandable or full view in verbose mode.
   - Clear failure states: `✗ execute_code  exited with code 1 · 0.4s`.
5. **Main Response Area**:
   - Rich Markdown streaming and rendering.
   - Clean visual hierarchy separating reasoning, tools, and assistant response.
6. **Input Area & Prompt**:
   - Distinct, elegant prompt: `❯ Ask Z.A.I.N.E anything... (or /help)`.
7. **Slash Command System**:
   - `/help`, `/mode [companion|code]`, `/persona [jarvis|ultron]`, `/status`, `/tools [query]`, `/model`, `/verbose [compact|normal|verbose]`, `/new`, `/history`, `/clear`, `/exit`.
   - Preserves all Cascade commands: `/code <prompt>`, `/inspect <file>`, `/run <file>`, `/test`, `/files`.
8. **Interruption & Cancellation**:
   - Graceful Ctrl+C handling: cancels in-flight stream/tool without killing the process; double Ctrl+C or `/exit` exits cleanly.
9. **Responsive Layout & Fallback**:
   - Width adaptations for 80, 100, 120, 160+ columns.
   - Windows terminal & PowerShell encoding/ANSI safety.

### B. Core Service Bridge & Integration
1. **`ui.py` (Minimal additive updates)**:
   - Add `GET /api/history` returning recent conversation episodes from SQLite.
   - Forward `think` and `routing` events over SSE.
2. **`agent.py` (Minimal additive updates)**:
   - Pass routing tier and reasoning tokens to `on_tool_event`.
3. **`zaine_cascade.py`**:
   - Integrated with `terminal_ui.py` to give Cascade the full modern terminal UX while retaining 100% of its coding commands.
4. **`terminal.py`**:
   - Dedicated CLI entry point.

## 4. Verification & Testing Plan
- Test startup capability banner rendering with real dynamic introspection.
- Test interactive chat and streaming response.
- Test tool execution display and duration tracking.
- Test persona switching (`/persona ultron` <-> `/persona jarvis`).
- Test slash commands (`/help`, `/status`, `/tools`, `/model`, `/verbose`, `/history`, `/new`, `/clear`).
- Test Code mode commands (`/code`, `/inspect`, `/files`).
- Test responsiveness across terminal widths (80, 120, 160 cols).
- Verify Phase 2a core service integrity and backward compatibility.
