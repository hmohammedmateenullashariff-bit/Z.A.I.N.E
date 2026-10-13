"""
Z.A.I.N.E Neural Command Textual Application
Stage 2: Wired to Core Service SSE Endpoint with Live Streaming, CoT, Tool Events, Timeouts & Cancellation.
"""

import sys
import time
import uuid
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple, Any

if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual import work, on
from textual.worker import Worker, WorkerState, get_current_worker
from textual.containers import Horizontal, Vertical
from textual.widgets import Input

from tui.widgets import (
    HeaderBar,
    NeuralBanner,
    ReasoningBlock,
    ToolLine,
    InputWell,
    AgentStateHUD,
    FooterBar,
    ChatLog,
    UserTurnCard,
    AssistantTurnCard,
    SystemCard,
    ApprovalCard,
    NeuralGraph3D,
    TopologyWorkspace,
)
from tui.telemetry import (
    get_vram_info,
    get_system_hardware,
    get_vault_stats,
    get_tool_registry_count,
    poll_hardware_telemetry,
    record_throughput_sample,
    TelemetrySnapshot,
)
from tui.client import (
    get_core_service_url,
    stream_chat_events,
    clear_context,
    get_system_status,
    set_persona_mode,
    toggle_voice,
    get_conversation_history,
    respond_to_approval,
    cancel_chat_request,
    StreamTimeoutError,
    StreamCancelledError,
)


class ZaineTUI(App):
    """Z.A.I.N.E Neural Terminal User Interface Application."""

    TITLE = "Z.A.I.N.E NEURAL"
    SUB_TITLE = "v3.5.0-alpha"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("f2", "toggle_hud", "Toggle HUD", show=False),
        Binding("f3", "toggle_workspace", "Toggle 3D Workspace", show=False),
        Binding("escape", "clear_focus", "Clear / Cancel", show=False),
        Binding("ctrl+c", "quit_app", "Quit", show=False),
    ]

    def __init__(self, core_url: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.core_url = core_url or get_core_service_url()
        self.is_streaming = False
        self._telemetry_stop_event = threading.Event()
        self.current_stream_worker: Optional[Worker] = None
        self._session_counter = 1
        self.current_session_id = f"SES-{datetime.now().strftime('%m%d')}-{self._session_counter:02d}"
        self.active_approval_card: Optional[ApprovalCard] = None
        self.active_request_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        """Compose layout matching DESIGN.md and multi-workspace architecture."""
        # Top Header Bar (Height 3)
        yield HeaderBar()

        # Workspace 1: Main Neural Command Center (Chat Pane ~70% / HUD ~30%)
        with Horizontal(id="chat-workspace"):
            with Vertical(id="chat-container"):
                yield ChatLog()
                yield InputWell()
            yield AgentStateHUD()

        # Workspace 2: Full-Screen Neural Topology & 3D Node Graph Dashboard
        yield TopologyWorkspace(id="topology-workspace")

        # Bottom Hardware Status Line (Height 1)
        yield FooterBar()

    def on_mount(self) -> None:
        """Set initial focus to input well, sync session IDs, and start background telemetry poller."""
        try:
            header = self.query_one(HeaderBar)
            footer = self.query_one(FooterBar)
            header.session_id = self.current_session_id
            footer.session_id = self.current_session_id
            input_box = self.query_one("#user-input", Input)
            input_box.focus()
        except Exception:
            pass

        # Start non-blocking 2s hardware telemetry poller (skipped in unit test runs)
        if not ("unittest" in sys.modules or "pytest" in sys.modules):
            self.poll_telemetry_loop()

    def on_unmount(self) -> None:
        """Clean shutdown of background threads."""
        self._telemetry_stop_event.set()

    @work(thread=True, name="telemetry_polling_worker")
    def poll_telemetry_loop(self) -> None:
        """Non-blocking background polling worker for CPU, RAM, and VRAM (2s interval)."""
        while not self._telemetry_stop_event.is_set():
            try:
                snapshot = poll_hardware_telemetry()
                self.call_from_thread(self._apply_telemetry_update, snapshot)
            except Exception:
                pass
            self._telemetry_stop_event.wait(2.0)

    def _apply_telemetry_update(self, snapshot: TelemetrySnapshot) -> None:
        """Dispatches telemetry updates to the UI thread without blocking the chat loop."""
        try:
            hud = self.query_one(AgentStateHUD)
            hud.update_telemetry(snapshot)
        except Exception:
            pass

    def action_toggle_workspace(self) -> None:
        """Toggle between Command Chat Workspace and 3D Topology Workspace (F2)."""
        chat_ws = self.query_one("#chat-workspace")
        topo_ws = self.query_one("#topology-workspace")
        header = self.query_one(HeaderBar)

        if topo_ws.display:
            # Switch back to Chat Workspace
            topo_ws.display = False
            chat_ws.display = True
            header.view_mode = "COMMAND"
            try:
                topo_ws.pause_animation()
            except Exception:
                pass
            try:
                input_box = self.query_one("#user-input", Input)
                input_box.focus()
            except Exception:
                pass
        else:
            # Switch to 3D Topology Workspace
            chat_ws.display = False
            topo_ws.display = True
            header.view_mode = "3D TOPOLOGY"
            try:
                topo_ws.resume_animation()
                canvas = topo_ws.query_one(NeuralGraph3D)
                canvas.focus()
            except Exception:
                pass

    def action_toggle_hud(self) -> None:
        """Toggles the Agent State HUD sidebar (F2 or /hud) to give full width to chat."""
        try:
            hud = self.query_one(AgentStateHUD)
            hud.display = not hud.display
        except Exception:
            pass

    def action_clear_focus(self) -> None:
        """Cancel active stream or clear input line / unfocus (Esc)."""
        if self.is_streaming:
            self.cancel_active_stream()
            return

        try:
            input_box = self.query_one("#user-input", Input)
            if input_box.value:
                input_box.value = ""
            else:
                self.set_focus(None)
        except Exception:
            pass

    def action_quit_app(self) -> None:
        """Cancel stream or perform clean exit (Ctrl+C)."""
        self._is_quitting = True
        if self.is_streaming:
            self.cancel_active_stream()
            return
        self.exit()

    def cancel_active_stream(self) -> None:
        """Cancels any running response stream worker and informs coordinator."""
        if self.active_request_id:
            try:
                import asyncio
                asyncio.create_task(cancel_chat_request(self.active_request_id, base_url=self.core_url))
            except Exception:
                pass

        if self.current_stream_worker and not self.current_stream_worker.is_finished:
            try:
                self.current_stream_worker.cancel()
            except Exception:
                pass

        self.is_streaming = False
        try:
            chat_log = self.query_one(ChatLog)
            chat_log.add_system_card(
                title="STREAM INTERRUPTED",
                message="Response generation was cancelled by the operator [Esc].",
                level="cancelled"
            )
            input_well = self.query_one(InputWell)
            input_well.set_generating(False)

            header = self.query_one(HeaderBar)
            footer = self.query_one(FooterBar)
            header.status_label = "READY"
            footer.status = "READY"
        except Exception:
            pass

    @on(ApprovalCard.Decision)
    async def on_approval_decision(self, event: ApprovalCard.Decision) -> None:
        """Handle interactive button click on ApprovalCard."""
        await self.resolve_approval(event.proposal_id, event.decision)

    @work
    async def resolve_approval_command(self, proposal_id: str, decision: str) -> None:
        """Execute approval resolution in worker thread."""
        await self.resolve_approval(proposal_id, decision)

    async def resolve_approval(self, proposal_id: str, decision: str) -> None:
        """Forwards user decision to POST /api/approval/respond."""
        res = await respond_to_approval(proposal_id=proposal_id, decision=decision, base_url=self.core_url)
        note = res.get("message", f"Turn updated: {decision}")
        if self.active_approval_card and self.active_approval_card.proposal_id == proposal_id:
            self.active_approval_card.set_resolved(decision, note=note)
            self.active_approval_card = None

        header = self.query_one(HeaderBar)
        footer = self.query_one(FooterBar)
        status_txt = "APPROVED" if decision == "approve" else "DENIED"
        header.status_label = status_txt
        footer.status = status_txt

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user message submission."""
        raw_text = event.value.strip()
        if not raw_text:
            return

        # Clear input field immediately
        event.input.value = ""

        # Reject regular turns while streaming unless it is an approval command or shortcut
        if self.is_streaming:
            cmd = raw_text.strip().lower()
            is_approval_cmd = (
                cmd in ("/approve", "/deny", "y", "n", "yes", "no")
                or cmd.startswith("/approve ")
                or cmd.startswith("/deny ")
            )
            if not is_approval_cmd:
                return

        # Process commands / queries
        self._dispatch_user_turn(raw_text)

    def _dispatch_user_turn(self, text: str) -> None:
        """Dispatch slash command or start chat turn stream."""
        cmd = text.strip().lower()

        # 0. Approval Slash Commands / Quick Keys
        if cmd == "/approve" or cmd.startswith("/approve ") or (self.active_approval_card and self.active_approval_card.status == "PENDING" and cmd in ("y", "yes")):
            parts = text.strip().split()
            target_id = parts[1] if len(parts) > 1 and parts[1].startswith("ACT-") else (self.active_approval_card.proposal_id if self.active_approval_card else "")
            if target_id:
                self.resolve_approval_command(target_id, "approve")
            return

        if cmd == "/deny" or cmd.startswith("/deny ") or (self.active_approval_card and self.active_approval_card.status == "PENDING" and cmd in ("n", "no")):
            parts = text.strip().split()
            target_id = parts[1] if len(parts) > 1 and parts[1].startswith("ACT-") else (self.active_approval_card.proposal_id if self.active_approval_card else "")
            if target_id:
                self.resolve_approval_command(target_id, "deny")
            return

        # 1. Local Slash Commands
        if cmd in ("/exit", "/quit", "exit", "quit"):
            self.exit()
            return

        if cmd == "/clear":
            chat_log = self.query_one(ChatLog)
            chat_log.clear_history()
            return

        if cmd == "/hud":
            self.action_toggle_hud()
            return

        if cmd == "/help":
            self._handle_help_command(text)
            return

        # 2. Backend Slash Commands
        if cmd == "/new":
            self.handle_new_session_command(text)
            return

        if cmd == "/status":
            self.handle_status_command(text)
            return

        if cmd == "/persona" or cmd.startswith("/persona ") or cmd == "/mode" or cmd.startswith("/mode "):
            self.handle_persona_command(text)
            return

        if cmd == "/voice" or cmd.startswith("/voice "):
            self.handle_voice_command(text)
            return

        if cmd == "/history":
            self.handle_history_command(text)
            return

        if cmd == "/memory":
            self.handle_memory_command(text)
            return

        if cmd == "/models":
            self.handle_models_command(text)
            return

        # 3. Standard User Natural Language Chat Turn (Streamed SSE)
        self.stream_agent_response(text)

    # --- Slash Command Handlers ---

    def _handle_help_command(self, user_text: str) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_user_message(user_text)
        help_md = (
            "### Z.A.I.N.E Neural Command System Index\n\n"
            "| Command / Key | Function |\n"
            "| :--- | :--- |\n"
            "| `/help` | Show command palette reference |\n"
            "| `/new` | Clear working memory & start fresh session (`/api/context/clear`) |\n"
            "| `/status` | Query live system telemetry, VRAM, and daemon health |\n"
            "| `/persona [jarvis\\|ultron]` | Switch persona protocol mode |\n"
            "| `/voice [on\\|off\\|status]` | Command-gated speech state control |\n"
            "| `/memory` | Inspect Obsidian durable knowledge vault index |\n"
            "| `/history` | View episodic memory session summaries |\n"
            "| `/models` | Inspect cognitive model tier configurations |\n"
            "| `/clear` | Clear chat viewport back to initial banner |\n"
            "| `/hud` or `[F2]` | Toggle Agent State HUD sidebar |\n"
            "| `[Esc]` | Cancel live stream / Clear prompt field |\n"
            "| `[Ctrl+C]` or `/exit` | Graceful application shutdown |\n"
        )
        chat_log.add_assistant_message(help_md, latency="0.01s")

    @work
    async def handle_new_session_command(self, user_text: str) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_user_message(user_text)

        res = await clear_context(self.core_url)
        self._session_counter += 1
        self.current_session_id = f"SES-{datetime.now().strftime('%m%d')}-{self._session_counter:02d}"

        header = self.query_one(HeaderBar)
        footer = self.query_one(FooterBar)
        header.session_id = self.current_session_id
        footer.session_id = self.current_session_id

        msg = res.get("message", "Working context cleared.")
        chat_log.add_system_card(
            title="SESSION REINITIALIZED",
            message=f"{msg}\nActive Session ID: `{self.current_session_id}`.\n*Durable Obsidian memory vault preserved.*",
            level="success"
        )

    @work
    async def handle_status_command(self, user_text: str) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_user_message(user_text)
        tool_line = chat_log.start_tool_line("system_status", "query=live_telemetry")

        t_start = time.perf_counter()
        res = await get_system_status(self.core_url)
        tool_line.set_done(duration_s=time.perf_counter() - t_start, status="COMPLETED")

        hw = get_system_hardware()
        vram = get_vram_info()
        tool_count = get_tool_registry_count()
        core_raw = res.get("status", "offline")
        if core_raw in ("idle", "ready", "ok", "online"):
            core_status = "online"
        elif core_raw == "error":
            core_status = "error (timeout/offline)"
        else:
            core_status = core_raw
        active_model = res.get("active_model", "zaine-reflex-7b")

        status_md = (
            "### Live Telemetry & Core Status\n\n"
            f"- **Daemon Port / Base**: `{self.core_url}` (State: `{core_status}`)\n"
            f"- **CPU Utilization**: `{hw['cpu']}`\n"
            f"- **System RAM**: `{hw['ram']}`\n"
            f"- **GPU / VRAM**: `{vram['display']}`\n"
            f"- **Registered Tools**: `{tool_count}` operational units\n"
            f"- **Active Model**: `{active_model}`\n"
            f"- **Coordinator Queue**: `0 in-flight`\n"
        )
        chat_log.add_assistant_message(status_md, latency=f"{time.perf_counter() - t_start:.2f}s")

    @work
    async def handle_persona_command(self, user_text: str) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_user_message(user_text)

        parts = user_text.strip().split()
        target_mode = parts[1].lower() if len(parts) > 1 else None

        res = await set_persona_mode(self.core_url, mode=target_mode)
        active_mode = res.get("mode", target_mode or "jarvis").upper()

        header = self.query_one(HeaderBar)
        footer = self.query_one(FooterBar)
        hud = self.query_one(AgentStateHUD)

        header.persona = active_mode
        footer.persona = active_mode
        hud.update_metrics(persona=active_mode)

        chat_log.add_system_card(
            title=f"PERSONA PROTOCOL: {active_mode}",
            message=res.get("message", f"Active persona mode set to {active_mode}."),
            level="info"
        )

    @work
    async def handle_voice_command(self, user_text: str) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_user_message(user_text)

        parts = user_text.strip().split()
        sub = parts[1].lower() if len(parts) > 1 else "toggle"

        enable_flag = None
        if sub == "on":
            enable_flag = True
        elif sub == "off":
            enable_flag = False

        res = await toggle_voice(self.core_url, enable=enable_flag)
        enabled = res.get("enabled", False)
        header = self.query_one(HeaderBar)
        header.voice_enabled = enabled

        state_str = "ENABLED (Speech Active)" if enabled else "DISABLED (Text-Only Mode)"
        chat_log.add_system_card(
            title=f"VOICE PROTOCOL: {state_str}",
            message=res.get("message", f"Voice state machine is now {state_str}."),
            level="info" if enabled else "warning"
        )

    @work
    async def handle_history_command(self, user_text: str) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_user_message(user_text)

        res = await get_conversation_history(self.core_url)
        episodes = res.get("episodes", [])
        if not episodes:
            chat_log.add_assistant_message("No past episodic memory records found in local memory index.", latency="0.02s")
            return

        lines = ["### Episodic Memory History (Recent Sessions)\n"]
        for ep in episodes[:5]:
            lines.append(f"- **{ep.get('session_start', 'Session')}**: {ep.get('topic_summary', 'No summary')}")
        chat_log.add_assistant_message("\n".join(lines), latency="0.03s")

    def handle_memory_command(self, user_text: str) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_user_message(user_text)
        tool_line = chat_log.start_tool_line("vault_index", "source='Obsidian'")

        v_stats = get_vault_stats()
        tool_line.set_done(duration_s=0.02, status="COMPLETED")

        mem_md = (
            "### Memory Subsystem & Obsidian Vault\n\n"
            f"- **Vault Connection**: `{v_stats['status']}`\n"
            f"- **Indexed Markdown Files**: `{v_stats['total_notes']}` notes\n"
            f"- **Context Budget**: `{v_stats['max_chars']}` characters\n"
            f"- **Security Policy**: Entity isolation & Prompt Injection boundaries active.\n"
        )
        chat_log.add_assistant_message(mem_md, latency="0.02s")

    def handle_models_command(self, user_text: str) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_user_message(user_text)

        models_md = (
            "### Cognitive Neural Models & Tiers\n\n"
            "| Tier | Target Model | Purpose |\n"
            "| :--- | :--- | :--- |\n"
            "| **Tier 0 (Reflex)** | `zaine-reflex-7b` | Conversational intent, fast routing & companionship |\n"
            "| **Tier 1 (Coder)** | `zaine-coder-7b` | Autonomous code synthesis & test generation |\n"
            "| **Tier 2 (Reasoning)** | `zaine-reflex-7b` | Chain-of-Thought multi-step analytical reasoning |\n"
            "| **Tier 3 (Vision)** | `moondream:latest` | Multimodal screen diagnostics & image inspection |\n"
        )
        chat_log.add_assistant_message(models_md, latency="0.01s")

    # --- SSE Stream Chat Turn Runner ---

    @work(exclusive=True)
    async def stream_agent_response(self, prompt: str) -> None:
        """Streams assistant response over SSE from CoreService."""
        self.is_streaming = True
        self.current_stream_worker = get_current_worker()

        chat_log = self.query_one(ChatLog)
        header = self.query_one(HeaderBar)
        footer = self.query_one(FooterBar)
        hud = self.query_one(AgentStateHUD)
        input_well = self.query_one(InputWell)

        # 1. Mount User Turn Card
        chat_log.add_user_message(prompt)

        # 2. Update visual status
        header.status_label = "THINKING"
        footer.status = "THINKING"
        input_well.set_generating(True)

        # Telemetry measurement trackers
        t_start = time.perf_counter()
        t_first_token: Optional[float] = None
        token_count = 0

        req_id = f"term-{uuid.uuid4().hex[:8]}"
        self.active_request_id = req_id

        active_reasoning_block: Optional[ReasoningBlock] = None
        active_tool_lines: Dict[str, Tuple[ToolLine, float]] = {}
        active_assistant_card: Optional[AssistantTurnCard] = None

        try:
            async for event in stream_chat_events(
                message=prompt,
                base_url=self.core_url,
                client_id="terminal-ui",
                request_id=req_id,
                default_first_token_timeout=60.0,
                idle_gap_timeout=20.0,
            ):
                # Check for cancellation
                if not self.is_streaming:
                    break

                ev_type = event.get("type")

                # A. Queued in Coordinator
                if ev_type == "queued":
                    pos = event.get("position", 1)
                    header.status_label = f"QUEUED #{pos}"
                    footer.status = f"QUEUED #{pos}"

                # B. Running / Thinking
                elif ev_type == "running":
                    header.status_label = "THINKING"
                    footer.status = "THINKING"

                # C. Tool & Cognitive Tier Events
                elif ev_type == "tool_event":
                    stage = event.get("stage", "")
                    tool_name = event.get("tool", "")
                    data = event.get("data", "")

                    if stage == "route":
                        if isinstance(data, dict):
                            tier = data.get("tier", "REFLEX")
                            m = data.get("model", "zaine-reflex-7b")
                            header.mode = tier
                            footer.model = m
                            hud.update_metrics(model=m, tier=tier)

                    elif stage == "think":
                        if active_reasoning_block is None:
                            active_reasoning_block = chat_log.start_reasoning_block()
                        active_reasoning_block.stream_token(str(data))
                        header.status_label = "REASONING"
                        footer.status = "REASONING"

                    elif stage == "think_done":
                        if active_reasoning_block:
                            active_reasoning_block.mark_complete()
                        header.status_label = "THINKING"
                        footer.status = "THINKING"

                    elif stage == "start":
                        args_sum = str(data)[:60] if data else ""
                        tool_line = chat_log.start_tool_line(tool_name, args_sum)
                        active_tool_lines[tool_name] = (tool_line, time.perf_counter())
                        header.status_label = f"TOOL: {tool_name}"
                        footer.status = f"TOOL: {tool_name}"

                    elif stage == "approval_required":
                        prop_data = data if isinstance(data, dict) else {}
                        pid = prop_data.get("proposal_id", "")
                        cmd_str = prop_data.get("command", "")
                        reason_str = prop_data.get("reason", "")
                        card = chat_log.add_approval_card(
                            proposal_id=pid,
                            command=cmd_str,
                            reason=reason_str,
                            tool_name=tool_name,
                        )
                        self.active_approval_card = card
                        header.status_label = "APPROVAL REQ"
                        footer.status = "APPROVAL REQ"

                    elif stage == "approval_wait":
                        header.status_label = "AWAITING APPROVAL"
                        footer.status = "AWAITING APPROVAL"

                    elif stage == "done":
                        if self.active_approval_card:
                            self.active_approval_card.set_resolved("APPROVED", "Action executed")
                            self.active_approval_card = None
                        if tool_name in active_tool_lines:
                            tool_line, t_tstart = active_tool_lines[tool_name]
                            dur = time.perf_counter() - t_tstart
                            tool_line.set_done(duration_s=dur, status="COMPLETED")
                            hud.add_tool_run(tool_name, duration_s=dur, status="COMPLETED")
                        header.status_label = "THINKING"
                        footer.status = "THINKING"

                # D. Streamed Token
                elif ev_type == "token":
                    content = event.get("content", "")
                    if t_first_token is None:
                        t_first_token = time.perf_counter()
                        ttft_ms = (t_first_token - t_start) * 1000.0
                        hud.update_metrics(ttft=f"{ttft_ms:.0f}ms", stream_active=True)

                    token_count += 1
                    header.status_label = "STREAMING"
                    footer.status = "STREAMING"

                    # Live throughput sparkline updates
                    if token_count % 3 == 0:
                        stream_elapsed = max(time.perf_counter() - (t_first_token or t_start), 0.001)
                        inst_rate = token_count / stream_elapsed
                        record_throughput_sample(inst_rate)
                        hud.update_metrics(
                            throughput=f"{inst_rate:.1f} tok/s",
                            stream_active=True
                        )

                    if active_assistant_card is None:
                        active_assistant_card = chat_log.start_assistant_turn(model=footer.model)

                    active_assistant_card.append_token(content)
                    chat_log.scroll_end(animate=False)

                # E. Done Event
                elif ev_type == "done":
                    t_end = time.perf_counter()
                    total_dur = t_end - t_start
                    stream_span = max(t_end - (t_first_token or t_start), 0.001)
                    tok_sec = token_count / stream_span if token_count > 0 else 0.0
                    th_str = f"{tok_sec:.1f} tok/s" if tok_sec > 0 else "n/a"

                    if tok_sec > 0:
                        record_throughput_sample(tok_sec)
                    hud.update_metrics(throughput=th_str, stream_active=False)

                    mode = event.get("mode")
                    if mode:
                        header.persona = mode.upper()
                        footer.persona = mode.upper()
                        hud.update_metrics(persona=mode.upper())

                    if active_assistant_card:
                        active_assistant_card.set_final(latency=f"{total_dur:.2f}s", throughput=th_str)
                    elif event.get("reply"):
                        # If completed without streaming token events (cached turn)
                        chat_log.add_assistant_message(
                            event.get("reply", ""),
                            model=footer.model,
                            latency=f"{total_dur:.2f}s",
                            throughput=th_str
                        )
                    chat_log.scroll_end(animate=False)
                    break

                # F. Error Event
                elif ev_type == "error":
                    err_msg = event.get("message", "Core service error")
                    chat_log.add_system_card(title="Core Stream Error", message=err_msg, level="error")
                    break

        except StreamTimeoutError as te:
            chat_log.add_system_card(title="Request Timeout", message=str(te), level="timeout")

        except (StreamCancelledError, asyncio.CancelledError):
            chat_log.add_system_card(
                title="STREAM INTERRUPTED",
                message="Response generation was cancelled by the operator [Esc].",
                level="cancelled"
            )

        except Exception as e:
            chat_log.add_system_card(title="Stream Transport Error", message=str(e), level="error")

        finally:
            hud.update_metrics(stream_active=False)
            self.is_streaming = False
            self.current_stream_worker = None
            self.active_request_id = None
            self.active_approval_card = None
            header.status_label = "READY"
            footer.status = "READY"
            input_well.set_generating(False)
            try:
                input_well.input_field.focus()
            except Exception:
                pass


def run() -> None:
    """Run Z.A.I.N.E TUI application."""
    app = ZaineTUI()
    app.run()


if __name__ == "__main__":
    run()
