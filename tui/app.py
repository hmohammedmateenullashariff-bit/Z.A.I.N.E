"""
Z.A.I.N.E Neural Command Textual Application
Stage 2: Wired to Core Service SSE Endpoint with Live Streaming, CoT, Tool Events, Timeouts & Cancellation.
"""

import sys
from zaine_env import running_under_tests
import json
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
from tui.exec_graph import ExecGraph, classify_tool_result, OK as NODE_OK, FAILED as NODE_FAILED, CANCELLED as NODE_CANCELLED
from tui.system_graph import collect_system_graph
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
    get_agents,
    set_agent,
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
        Binding("f3", "toggle_workspace", "Toggle graph workspace", show=False),
        Binding("escape", "clear_focus", "Clear / Cancel", show=False),
        # priority: the focused Input otherwise swallows Ctrl+C as "copy"
        Binding("ctrl+c", "quit_app", "Cancel / Quit", show=False, priority=True),
        Binding("ctrl+q", "quit_now", "Quit", show=False, priority=True),
    ]

    SYSTEM_POLL_EVERY = 3  # telemetry ticks (2s each) between system-topology collections

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
        self.exec_graph = ExecGraph()
        self.system_facts: Dict[str, Any] = {}

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
            self.query_one(AgentStateHUD).exec_graph = self.exec_graph
            self.query_one(TopologyWorkspace).set_exec_graph(self.exec_graph)
        except Exception:
            pass

        # Telemetry + core/system status run in a thread (blocking HTTP stays off the UI loop).
        if not running_under_tests():
            self.poll_telemetry_loop()

    def on_unmount(self) -> None:
        """Clean shutdown of background threads."""
        self._telemetry_stop_event.set()

    @work(thread=True, name="telemetry_polling_worker", group="telemetry")
    def poll_telemetry_loop(self) -> None:
        """Hardware telemetry every 2s; core/Ollama/system topology every SYSTEM_POLL_EVERY ticks."""
        tick = 0
        while not self._telemetry_stop_event.is_set():
            try:
                snapshot = poll_hardware_telemetry()
                self.call_from_thread(self._apply_telemetry_update, snapshot)
            except Exception:
                pass
            if tick % self.SYSTEM_POLL_EVERY == 0:
                try:
                    graph = collect_system_graph(self.core_url)
                    self.call_from_thread(self._apply_system_graph, graph)
                except Exception:
                    pass
            tick += 1
            self._telemetry_stop_event.wait(2.0)

    def _idle_status(self) -> str:
        """Status label when no turn is running, from the last real core poll (READY until the first poll)."""
        facts = self.system_facts
        if not facts:
            return "READY"
        status = facts.get("core_status") or {}
        if not facts.get("core_up"):
            return "OFFLINE"
        if status.get("warming"):
            return "WARMING UP"
        return "READY" if status.get("model_loaded") else "NO MODEL"

    def _apply_system_graph(self, graph: Any) -> None:
        """Pushes the real system topology to the graph view and derives the idle status line from it."""
        facts = getattr(graph, "facts", {}) or {}
        self.system_facts = facts
        try:
            self.query_one(TopologyWorkspace).set_system_graph(graph)
            hud = self.query_one(AgentStateHUD)
            hud.core_online = bool(facts.get("core_up"))
            header = self.query_one(HeaderBar)
            footer = self.query_one(FooterBar)
            status = facts.get("core_status") or {}
            cfg = status.get("config") or {}
            flags = [name for name, on in (("DEMO", cfg.get("demo")), ("FAST 3B", cfg.get("fast"))) if on]
            header.core_flags = " · ".join(flags) if facts.get("core_up") else ""
            # Keep the pin indicator in sync (Telegram or another client may change it).
            agent_info = status.get("agent") or {}
            if facts.get("core_up") and not self.is_streaming:
                header.agent_pinned = bool(agent_info.get("pinned"))
                hud.agent_pinned = header.agent_pinned
            if not self.is_streaming:
                label = self._idle_status()
                header.status_label = label
                footer.status = label
                model = status.get("active_model")
                if model:
                    footer.model = model
                    if hud.active_model == "n/a":
                        hud.update_metrics(model=model)
                mode = status.get("mode")
                if mode:
                    header.persona = footer.persona = mode.upper()
                    hud.update_metrics(persona=mode.upper())
            hud.refresh()
        except Exception:
            pass

    def _refresh_graph_views(self) -> None:
        """Repaints the live trace (HUD) and, when visible, the execution DAG."""
        try:
            self.query_one(AgentStateHUD).refresh()
            self.query_one(TopologyWorkspace).refresh_exec()
        except Exception:
            pass

    def _apply_telemetry_update(self, snapshot: TelemetrySnapshot) -> None:
        """Dispatches telemetry updates to the UI thread without blocking the chat loop."""
        try:
            hud = self.query_one(AgentStateHUD)
            hud.update_telemetry(snapshot)
        except Exception:
            pass

    def action_toggle_workspace(self) -> None:
        """Toggle between the command view and the graph workspace (F3)."""
        chat_ws = self.query_one("#chat-workspace")
        topo_ws = self.query_one(TopologyWorkspace)
        header = self.query_one(HeaderBar)

        if topo_ws.display:
            topo_ws.display = False
            chat_ws.display = True
            header.view_mode = "COMMAND"
            try:
                topo_ws.pause_animation()
            except Exception:
                pass
            try:
                self.query_one("#user-input", Input).focus()
            except Exception:
                pass
        else:
            chat_ws.display = False
            topo_ws.display = True
            header.view_mode = "GRAPH"
            try:
                topo_ws.resume_animation()
                topo_ws.focus_canvas()
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
        """Ctrl+C: cancel the reply if one is streaming, otherwise exit."""
        if self.is_streaming:
            self.cancel_active_stream()
            return
        self.exit()

    def action_quit_now(self) -> None:
        """Ctrl+Q: cancel anything running and exit."""
        if self.is_streaming:
            self.cancel_active_stream()
        self.exit()

    def cancel_active_stream(self) -> None:
        """Cancels the running stream worker; the worker itself records the interruption card."""
        if self.active_request_id:
            # Keep a reference so the cancel request is not garbage-collected mid-flight.
            self._cancel_task = asyncio.create_task(cancel_chat_request(self.active_request_id, base_url=self.core_url))

        if self.current_stream_worker and not self.current_stream_worker.is_finished:
            try:
                self.current_stream_worker.cancel()
            except Exception:
                pass

        self.is_streaming = False
        try:
            self.query_one(InputWell).set_generating(False)
            self.query_one(HeaderBar).status_label = self._idle_status()
            self.query_one(FooterBar).status = self._idle_status()
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
        # Show what the server actually recorded; a decision on an expired or already-decided
        # proposal comes back ok=False and must not be drawn as approved/denied.
        if res.get("ok"):
            status_txt = "APPROVED" if decision == "approve" else "DENIED"
        else:
            status_txt = "NOT APPLIED"
        if self.active_approval_card and self.active_approval_card.proposal_id == proposal_id:
            self.active_approval_card.set_resolved(status_txt, note=note)
            self.active_approval_card = None

        header = self.query_one(HeaderBar)
        footer = self.query_one(FooterBar)
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
            # A bare y/n with no pending card would otherwise start a new turn and cancel this stream.
            card_pending = self.active_approval_card and self.active_approval_card.status == "PENDING"
            if cmd in ("y", "n", "yes", "no") and not card_pending:
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

        if cmd == "/agent" or cmd.startswith("/agent ") or cmd == "/agents":
            self.handle_agent_command(text)
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
            "| `/agent [name\\|auto]` | List VisionQuest agents, pin one, or restore auto routing |\n"
            "| `@edith …` / `@ultron …` | Send one message to a specific agent |\n"
            "| `/clear` | Clear chat viewport back to initial banner |\n"
            "| `/hud` or `F2` | Toggle Agent State HUD sidebar |\n"
            "| `F3` | Graph workspace: `1` live execution DAG · `2` system topology · `3` 3D orbit |\n"
            "| `Esc` | Cancel live stream / clear prompt field |\n"
            "| `y` / `n` | Approve / reject the pending guardrail card |\n"
            "| `Ctrl+C` | Cancel the reply; exits when nothing is running |\n"
            "| `Ctrl+Q` or `/exit` | Quit |\n"
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
        active_model = res.get("active_model") or "n/a (core offline)"

        status_md = (
            "### Live Telemetry & Core Status\n\n"
            f"- **Daemon Port / Base**: `{self.core_url}` (State: `{core_status}`)\n"
            f"- **CPU Utilization**: `{hw['cpu']}`\n"
            f"- **System RAM**: `{hw['ram']}`\n"
            f"- **GPU / VRAM**: `{vram['display']}`\n"
            f"- **Clustered Tools**: `{tool_count}`\n"
            f"- **Active Model**: `{active_model}`\n"
        )
        loaded = self.system_facts.get("loaded_models") or []
        if loaded:
            status_md += "- **Resident in VRAM**: " + ", ".join(f"`{n}` ({v:.1f} GB)" for n, v in loaded) + "\n"
        pending = self.system_facts.get("pending_approvals")
        if pending is not None:
            status_md += f"- **Pending approvals**: `{pending}`\n"
        status_md += f"- **Telegram poller**: `{'online' if self.system_facts.get('telegram_online') else 'off'}`\n"
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
        self.query_one(FooterBar).voice_enabled = enabled
        hud = self.query_one(AgentStateHUD)
        hud.voice_enabled = enabled
        hud.refresh()

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

    @work
    async def handle_agent_command(self, user_text: str) -> None:
        """/agent lists the VisionQuest agents; /agent <name> pins one; /agent auto restores routing."""
        chat_log = self.query_one(ChatLog)
        chat_log.add_user_message(user_text)
        parts = user_text.strip().split(maxsplit=1)
        header = self.query_one(HeaderBar)
        hud = self.query_one(AgentStateHUD)

        if len(parts) > 1:
            res = await set_agent(parts[1], base_url=self.core_url)
            ok = bool(res.get("ok"))
            chat_log.add_system_card(
                title="AGENT PINNED" if ok and res.get("pinned") else ("AUTO ROUTING" if ok else "AGENT NOT CHANGED"),
                message=res.get("message", ""),
                level="success" if ok else "warning",
            )
            if ok:
                header.agent_pinned = bool(res.get("pinned"))
                if res.get("display_name"):
                    header.agent_name = res["display_name"]
                hud.agent_pinned = header.agent_pinned
                hud.refresh()
            return

        res = await get_agents(base_url=self.core_url)
        agents = res.get("agents") or []
        if not agents:
            chat_log.add_system_card(title="AGENTS UNAVAILABLE", message=res.get("message", "Core is offline."), level="warning")
            return
        pinned = res.get("pinned")
        last = (res.get("last") or {}).get("agent_id")
        rows = ["### VisionQuest Agents\n",
                "| Agent | Role | Tools | Routing | Call it |",
                "| :--- | :--- | :--- | :--- | :--- |"]
        for a in agents:
            mark = " (pinned)" if a["agent_id"] == pinned else (" (last turn)" if a["agent_id"] == last else "")
            routing = "background" if not a.get("interactive") else ("auto" if a.get("auto_route") else "on request")
            alias = (a.get("aliases") or [a["agent_id"]])[0]
            call = f"`@{alias}` · `/agent {alias}`" if a.get("interactive") else "—"
            rows.append(f"| **{a['display_name']}**{mark} | {a['title']} | {a['tool_count']} | {routing} | {call} |")
        rows.append("\nAgents can consult each other with `ask_agent` (one level deep). `/agent auto` restores automatic routing.")
        chat_log.add_assistant_message("\n".join(rows), latency="0.01s")

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
            f"- **Context Budget**: `{v_stats['max_chars']}` characters per turn\n"
        )
        folders = {k: v for k, v in (v_stats.get("folders") or {}).items() if v}
        if folders:
            mem_md += "- **Folders**: " + ", ".join(f"`{k}` {v}" for k, v in sorted(folders.items())) + "\n"
        chat_log.add_assistant_message(mem_md, latency="0.02s")

    def handle_models_command(self, user_text: str) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_user_message(user_text)

        # Routing comes from core_router (the same rules the core uses); residency is from Ollama /api/ps.
        try:
            from core_router import router
            tiers = [("Reflex (chat, tools)", router.reflex_model), ("Deep reasoning", router.deep_model),
                     ("Coder", router.coder_model), ("Vision", "moondream:latest")]
        except Exception:
            tiers = []
        loaded = {n for n, _ in (self.system_facts.get("loaded_models") or [])}
        models_md = "### Model Routing\n\n| Tier | Model | In VRAM now |\n| :--- | :--- | :--- |\n"
        for tier, model in tiers:
            short = model.replace(":latest", "")
            models_md += f"| {tier} | `{model}` | {'yes' if short in loaded else 'no'} |\n"
        if not tiers:
            models_md += "| n/a | router unavailable | |\n"
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

        # 1. Mount User Turn Card and start this turn's execution graph
        chat_log.add_user_message(prompt)
        self.exec_graph.start_turn(prompt)
        self._refresh_graph_views()

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
        # tool name -> running lines in start order (the same tool can run twice in one turn)
        active_tool_lines: Dict[str, list] = {}
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
                self.exec_graph.apply(event)
                self._refresh_graph_views()

                # Pre-warm event
                if ev_type == "warming":
                    header.status_label = "WARMING UP"
                    footer.status = "WARMING UP"

                # A. Queued in Coordinator
                elif ev_type == "queued":
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

                    elif stage == "agent":
                        info = data if isinstance(data, dict) else {}
                        name = str(info.get("display_name") or tool_name)
                        color = str(info.get("color") or "#00f5a0")
                        pinned = info.get("source") == "pinned"
                        header.agent_name, header.agent_color, header.agent_pinned = name, color, pinned
                        hud.update_agent(name, str(info.get("title", "")), str(info.get("reason", "")), color, pinned)

                    elif stage in ("delegate_start", "delegate_done"):
                        info = data if isinstance(data, dict) else {}
                        to_name = str(info.get("to_display") or tool_name)
                        label = f"CONSULTING {to_name}" if stage == "delegate_start" else "THINKING"
                        header.status_label = label
                        footer.status = label

                    elif stage == "profiler":
                        # Ollama's own counters for the call that just finished: the real tok/s.
                        info = data if isinstance(data, dict) else {}
                        eval_count = int(info.get("eval_count") or 0)
                        eval_s = float(info.get("eval_duration_s") or 0.0)
                        if eval_count and eval_s > 0:
                            rate = eval_count / eval_s
                            record_throughput_sample(rate)
                            hud.update_metrics(
                                throughput=f"{rate:.1f} tok/s",
                                eval_counts=f"{eval_count} out · {int(info.get('prompt_eval_count') or 0)} prompt",
                            )

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
                        if isinstance(data, dict):
                            args_sum = ", ".join(f"{k}={v}" for k, v in data.items())[:60]
                        else:
                            args_sum = str(data)[:60] if data else ""
                        tool_line = chat_log.start_tool_line(tool_name, args_sum)
                        active_tool_lines.setdefault(tool_name, []).append((tool_line, time.perf_counter()))
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
                            risk_level=str(prop_data.get("risk_level", "")),
                        )
                        for line, _t in active_tool_lines.get(tool_name, [])[:1]:
                            line.set_done(status="AWAITING APPROVAL")
                        self.active_approval_card = card
                        header.status_label = "APPROVAL REQ"
                        footer.status = "APPROVAL REQ"

                    elif stage == "approval_wait":
                        header.status_label = "AWAITING APPROVAL"
                        footer.status = "AWAITING APPROVAL"

                    elif stage == "done":
                        # The outcome comes from the tool's own result string: approvals may have been
                        # answered on Telegram or expired, and tools can fail.
                        tool_status, outcome = classify_tool_result(data)
                        if self.active_approval_card and self.active_approval_card.status == "PENDING":
                            note = "Action executed" if outcome == "APPROVED" else str(data)[:160]
                            self.active_approval_card.set_resolved(outcome, note)
                        self.active_approval_card = None
                        lines = active_tool_lines.get(tool_name) or []
                        if lines:
                            tool_line, t_tstart = lines.pop(0)
                            dur = time.perf_counter() - t_tstart
                            line_status = {"ok": "COMPLETED", "failed": "FAILED", "blocked": "BLOCKED"}.get(tool_status, "COMPLETED")
                            tool_line.set_done(duration_s=dur, status=line_status)
                            hud.add_tool_run(tool_name, duration_s=dur, status=line_status)
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
                    if header.status_label != "STREAMING":
                        header.status_label = "STREAMING"
                        footer.status = "STREAMING"
                    # Token events carry sentence chunks, not tokens; the real tok/s arrives with the
                    # `profiler` event from Ollama's eval counters.

                    if active_assistant_card is None:
                        active_assistant_card = chat_log.start_assistant_turn(model=footer.model)

                    active_assistant_card.append_token(content)
                    chat_log.scroll_end(animate=False)

                # E. Done Event
                elif ev_type == "done":
                    t_end = time.perf_counter()
                    total_dur = t_end - t_start
                    summary = self.exec_graph.summary()
                    th_str = f"{summary['tok_s']:.1f} tok/s" if summary["tok_s"] else "n/a"
                    hud.update_metrics(stream_active=False)

                    mode = event.get("mode")
                    if mode:
                        header.persona = mode.upper()
                        footer.persona = mode.upper()
                        hud.update_metrics(persona=mode.upper())

                    if active_assistant_card:
                        if event.get("reply"):
                            active_assistant_card.markdown_text = event.get("reply")
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
            self.exec_graph.abort(str(te))
            chat_log.add_system_card(title="Request Timeout", message=str(te), level="timeout")

        except (StreamCancelledError, asyncio.CancelledError):
            self.exec_graph.abort("cancelled by operator", status=NODE_CANCELLED)
            chat_log.add_system_card(
                title="STREAM INTERRUPTED",
                message="Response generation was cancelled by the operator (Esc / Ctrl+C).",
                level="cancelled"
            )

        except Exception as e:
            self.exec_graph.abort(str(e))
            chat_log.add_system_card(title="Stream Transport Error", message=str(e), level="error")

        finally:
            # Nothing may stay drawn as running once the turn is over.
            if self.exec_graph.is_active:
                self.exec_graph.abort("stream ended without a final event")
            for lines in active_tool_lines.values():
                for tool_line, _t in lines:
                    tool_line.set_done(duration_s=time.perf_counter() - _t, status="CANCELLED")
            if active_reasoning_block and not active_reasoning_block.is_complete:
                active_reasoning_block.mark_complete()
            if active_assistant_card and active_assistant_card.latency == "streaming...":
                active_assistant_card.set_final(latency=f"{time.perf_counter() - t_start:.2f}s (incomplete)")
            self._refresh_graph_views()
            hud.update_metrics(stream_active=False)
            # A cancelled turn finishes after a new one may already have started: only reset shared
            # state if it still belongs to this request.
            if self.active_request_id == req_id:
                if self.active_approval_card and self.active_approval_card.status == "PENDING":
                    self.active_approval_card.set_resolved("NOT EXECUTED", "The turn ended before a decision.")
                self.is_streaming = False
                self.current_stream_worker = None
                self.active_request_id = None
                self.active_approval_card = None
                header.status_label = self._idle_status()
                footer.status = self._idle_status()
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
