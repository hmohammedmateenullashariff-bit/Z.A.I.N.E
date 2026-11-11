"""
Z.A.I.N.E Neural Command Textual Application
Stage 2: Wired to Core Service SSE Endpoint with Live Streaming, CoT, Tool Events, Timeouts & Cancellation.
"""

import os
import sys
import atexit
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


def _restore_terminal_modes() -> None:
    """Disables mouse tracking and restores primary screen upon process termination."""
    try:
        if sys.platform == "win32":
            sys.stdout.write("\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?1015l\x1b[?1049l\x1b[?25h")
            sys.stdout.flush()
    except Exception:
        pass


atexit.register(_restore_terminal_modes)

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
    get_runs,
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
        Binding("f4", "toggle_obsidian_modal", "Obsidian Memory Graph", show=False),
        Binding("escape", "clear_focus", "Clear / Cancel", show=False),
        Binding("pageup", "scroll_page_up", "Scroll Up", priority=True, show=False),
        Binding("pagedown", "scroll_page_down", "Scroll Down", priority=True, show=False),
        Binding("shift+up", "scroll_line_up", "Scroll Line Up", priority=True, show=False),
        Binding("shift+down", "scroll_line_down", "Scroll Line Down", priority=True, show=False),
        Binding("ctrl+home", "scroll_to_home", "Scroll to Top", priority=True, show=False),
        Binding("ctrl+end", "scroll_to_end", "Scroll to Bottom", priority=True, show=False),
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

    @staticmethod
    def _format_queue_display(queue_info: Optional[Dict[str, Any]]) -> str:
        """Formats real RequestCoordinator queue telemetry without fake numbers."""
        if not isinstance(queue_info, dict) or not queue_info.get("ok", True):
            return "n/a"
        depth = int(queue_info.get("queue_depth") or 0)
        running = bool(queue_info.get("running"))
        if running:
            return f"{depth} queued (1 active)"
        return f"{depth} queued"

    @staticmethod
    def _agent_mode_enabled(facts: Optional[Dict[str, Any]] = None) -> bool:
        """Checks whether autonomous agent mode (ZAINE_AGENT=1) is enabled locally or on CoreService."""
        raw = os.getenv("ZAINE_AGENT")
        if raw is not None and raw.strip() != "":
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(facts, dict) and facts.get("core_up"):
            return bool(facts.get("agent_enabled"))
        return False

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
            if not facts.get("core_up"):
                hud.queue_display = "n/a"
            elif isinstance(facts.get("queue"), dict) and not self.is_streaming:
                hud.queue_display = self._format_queue_display(facts.get("queue"))
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

    def action_toggle_obsidian_modal(self) -> None:
        """Toggles the interactive Obsidian-style Memory Digraph modal popup (F4 or /graph)."""
        try:
            from tui.widgets.obsidian_modal import ObsidianMemoryModal
            self.push_screen(ObsidianMemoryModal())
        except Exception:
            pass

    def _is_graph_workspace_active(self) -> bool:
        try:
            return self.query_one(TopologyWorkspace).display
        except Exception:
            return False

    def action_scroll_page_up(self) -> None:
        if self._is_graph_workspace_active():
            try:
                topo = self.query_one(TopologyWorkspace)
                target = topo.query_one(f"#{topo.mode}")
                if hasattr(target, "scroll_page_up"):
                    target.scroll_page_up(animate=False)
            except Exception:
                pass
        else:
            try:
                self.query_one(ChatLog).scroll_page_up(animate=False)
            except Exception:
                pass

    def action_scroll_page_down(self) -> None:
        if self._is_graph_workspace_active():
            try:
                topo = self.query_one(TopologyWorkspace)
                target = topo.query_one(f"#{topo.mode}")
                if hasattr(target, "scroll_page_down"):
                    target.scroll_page_down(animate=False)
            except Exception:
                pass
        else:
            try:
                self.query_one(ChatLog).scroll_page_down(animate=False)
            except Exception:
                pass

    def action_scroll_line_up(self) -> None:
        if self._is_graph_workspace_active():
            try:
                topo = self.query_one(TopologyWorkspace)
                target = topo.query_one(f"#{topo.mode}")
                if hasattr(target, "scroll_up"):
                    target.scroll_up(animate=False)
            except Exception:
                pass
        else:
            try:
                self.query_one(ChatLog).scroll_up(animate=False)
            except Exception:
                pass

    def action_scroll_line_down(self) -> None:
        if self._is_graph_workspace_active():
            try:
                topo = self.query_one(TopologyWorkspace)
                target = topo.query_one(f"#{topo.mode}")
                if hasattr(target, "scroll_down"):
                    target.scroll_down(animate=False)
            except Exception:
                pass
        else:
            try:
                self.query_one(ChatLog).scroll_down(animate=False)
            except Exception:
                pass

    def action_scroll_to_home(self) -> None:
        if self._is_graph_workspace_active():
            try:
                topo = self.query_one(TopologyWorkspace)
                target = topo.query_one(f"#{topo.mode}")
                if hasattr(target, "scroll_home"):
                    target.scroll_home(animate=False)
            except Exception:
                pass
        else:
            try:
                self.query_one(ChatLog).scroll_home(animate=False)
            except Exception:
                pass

    def action_scroll_to_end(self) -> None:
        if self._is_graph_workspace_active():
            try:
                topo = self.query_one(TopologyWorkspace)
                target = topo.query_one(f"#{topo.mode}")
                if hasattr(target, "scroll_end"):
                    target.scroll_end(animate=False)
            except Exception:
                pass
        else:
            try:
                self.query_one(ChatLog).scroll_end(animate=False)
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
            hud = self.query_one(AgentStateHUD)
            hud.update_execution_state(
                tool_in_use="n/a",
                run_status="cancelled" if hud.run_id != "n/a" else None,
            )
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
        if cmd in ("/graph", "/digraph", "/obsidian", "/memory graph"):
            self.action_toggle_obsidian_modal()
            return

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

        if cmd == "/run" or cmd.startswith("/run "):
            self.handle_run_command(text)
            return

        if cmd == "/runs" or cmd.startswith("/runs "):
            self.handle_runs_command(text)
            return

        if cmd == "/stop" or cmd.startswith("/stop "):
            self.handle_stop_command(text)
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
            "| `/run <goal>` | Start an autonomous loop run (requires `ZAINE_AGENT=1`) |\n"
            "| `/runs [resumable\\|resume <id>]` | List autonomous runs & resume interrupted scratchpads |\n"
            "| `/stop` | Stop the active stream or autonomous run cleanly |\n"
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

        if sub in ("chat", "talk", "live"):
            # Enable voice output if not already enabled
            await toggle_voice(self.core_url, enable=True)
            self.query_one(HeaderBar).voice_enabled = True
            self.query_one(FooterBar).voice_enabled = True
            hud = self.query_one(AgentStateHUD)
            hud.voice_enabled = True
            hud.refresh()

            chat_log.add_system_card(
                title="🎤 VOICE CHAT ENGAGED",
                message="Listening for your voice... Speak your directive clearly into your microphone.\n"
                        "Z.A.I.N.E will transcribe your speech and answer via speech and text.",
                level="warning"
            )
            self.listen_voice_chat_worker()
            return

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

    @work(thread=True, name="voice_chat_listener_worker")
    def listen_voice_chat_worker(self) -> None:
        """Captures voice input from the microphone and dispatches into the chat stream."""
        try:
            import voice
            self.call_from_thread(self._set_voice_chat_status, True)
            spoken = voice.one_shot_listen(duration=7)
            self.call_from_thread(self._set_voice_chat_status, False)
            if spoken and spoken.strip():
                self.call_from_thread(self._on_voice_turn_captured, spoken.strip())
            else:
                self.call_from_thread(self._on_voice_turn_silence)
        except Exception as e:
            self.call_from_thread(self._set_voice_chat_status, False)
            self.call_from_thread(self._on_voice_turn_error, str(e))

    def _set_voice_chat_status(self, is_listening: bool) -> None:
        try:
            well = self.query_one(InputWell)
            well.set_generating(is_listening)
            if is_listening:
                well.query_one("#input-hints", Static).update("🎙 VOICE CHAT: Listening... Speak your prompt now (Esc to cancel)")
        except Exception:
            pass

    def _on_voice_turn_captured(self, spoken_text: str) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_system_card(title="✓ VOICE TRANSCRIBED", message=f"Heard: \"{spoken_text}\"", level="success")
        self._dispatch_user_turn(spoken_text)

    def _on_voice_turn_silence(self) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_system_card(
            title="VOICE CHAT: NO SPEECH DETECTED",
            message="No speech detected during 7s listening window. Type /voice chat to listen again.",
            level="info"
        )

    def _on_voice_turn_error(self, err_text: str) -> None:
        chat_log = self.query_one(ChatLog)
        chat_log.add_system_card(title="VOICE CHAT ERROR", message=f"Audio error: {err_text}", level="error")

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

    def handle_run_command(self, user_text: str) -> None:
        """/run <goal> launches an autonomous run; /run --resume <run_id> resumes from scratchpad."""
        chat_log = self.query_one(ChatLog)
        parts = user_text.strip().split(maxsplit=1)
        arg = parts[1].strip() if len(parts) > 1 else ""
        if not arg:
            chat_log.add_user_message(user_text)
            chat_log.add_system_card(
                title="AUTONOMOUS RUN USAGE",
                message="Usage: `/run <goal>` or `/run --resume <run_id>`.\nInspect persisted runs via `/runs`.",
                level="info",
            )
            return

        if not self._agent_mode_enabled(self.system_facts):
            chat_log.add_user_message(user_text)
            chat_log.add_system_card(
                title="AUTONOMOUS MODE DISABLED",
                message="Autonomous `/run` requires `ZAINE_AGENT=1`. Leave flag off for standard chat.",
                level="warning",
            )
            return

        resume_id: Optional[str] = None
        tokens = arg.split(maxsplit=1)
        head = tokens[0].lower()
        if head in ("--resume", "resume"):
            resume_id = tokens[1].strip() if len(tokens) > 1 else ""
            if not resume_id:
                chat_log.add_user_message(user_text)
                chat_log.add_system_card(
                    title="MISSING RUN ID",
                    message="Specify a run ID: `/run --resume <run_id>` (see `/runs`).",
                    level="warning",
                )
                return
            self.stream_agent_response(
                f"Resume run {resume_id}",
                force_autonomous=True,
                resume_run_id=resume_id,
                display_prompt=user_text,
            )
            return

        self.stream_agent_response(arg, force_autonomous=True, display_prompt=user_text)

    @work
    async def handle_runs_command(self, user_text: str) -> None:
        """/runs lists autonomous runs from scratchpad store; /runs resume <id> resumes one."""
        chat_log = self.query_one(ChatLog)
        parts = user_text.strip().split()
        if len(parts) >= 3 and parts[1].lower() in ("resume", "--resume"):
            target_id = parts[2].strip()
            if not self._agent_mode_enabled(self.system_facts):
                chat_log.add_user_message(user_text)
                chat_log.add_system_card(
                    title="AUTONOMOUS MODE DISABLED",
                    message="Resuming an autonomous run requires `ZAINE_AGENT=1`.",
                    level="warning",
                )
                return
            self.stream_agent_response(
                f"Resume run {target_id}",
                force_autonomous=True,
                resume_run_id=target_id,
                display_prompt=user_text,
            )
            return

        chat_log.add_user_message(user_text)
        resumable_only = len(parts) >= 2 and parts[1].lower() in ("resumable", "--resumable", "pending")
        res = await get_runs(resumable_only=resumable_only, base_url=self.core_url)
        if not res.get("ok"):
            chat_log.add_system_card(
                title="RUNS UNAVAILABLE",
                message=res.get("message", "Could not query /api/runs on CoreService."),
                level="warning",
            )
            return

        runs = res.get("runs") or []
        if not runs:
            chat_log.add_system_card(
                title="NO AUTONOMOUS RUNS",
                message="No persisted scratchpad runs found yet. Start one with `/run <goal>` (under `ZAINE_AGENT=1`).",
                level="info",
            )
            return

        rows = [
            "### Autonomous Run Scratchpads\n",
            "| Run ID | Agent | Status | Steps | Updated | Goal |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        resumable_ids = []
        for r in runs[:15]:
            rid = str(r.get("run_id") or "")
            agent_id = str(r.get("agent_id") or "n/a")
            eff_status = str(r.get("effective_status") or r.get("status") or "unknown")
            if r.get("resumable"):
                resumable_ids.append(rid)
            steps = f"{r.get('completed_steps', 0)}/{r.get('max_steps', '?')}"
            updated = str(r.get("updated_at") or "")[:19].replace("T", " ")
            goal = str(r.get("task") or "").replace("|", "\\|").replace("\n", " ")[:60]
            rows.append(f"| `{rid}` | {agent_id} | {eff_status} | {steps} | {updated} | {goal} |")

        if resumable_ids:
            rows.append(f"\nResumable runs found ({len(resumable_ids)}). Use `/run --resume {resumable_ids[0]}` or `/runs resume {resumable_ids[0]}`.")
        if not res.get("agent_enabled", True):
            rows.append("\n*Note: `ZAINE_AGENT=0` currently; enable `ZAINE_AGENT=1` to launch or resume runs.*")
        chat_log.add_assistant_message("\n".join(rows), latency="0.01s")

    @work
    async def handle_stop_command(self, user_text: str) -> None:
        """/stop cancels the active stream or running autonomous task cleanly."""
        chat_log = self.query_one(ChatLog)
        chat_log.add_user_message(user_text)
        req_id = self.active_request_id or ""
        parts = user_text.strip().split(maxsplit=1)
        run_id = parts[1].strip() if len(parts) > 1 else ""

        if self.is_streaming:
            self.cancel_active_stream()

        res = await cancel_chat_request(request_id=req_id, base_url=self.core_url, run_id=run_id)
        try:
            hud = self.query_one(AgentStateHUD)
            hud.update_execution_state(
                tool_in_use="n/a",
                run_status="cancelled" if res.get("ok") else hud.run_status,
            )
        except Exception:
            pass

        cancelled_n = res.get("cancelled_runs", 0)
        msg = "Active request and autonomous run cancelled cleanly." if res.get("ok") else res.get("message", "Cancel sent.")
        if cancelled_n:
            msg += f" ({cancelled_n} active autonomous run(s) stopped.)"
        chat_log.add_system_card(
            title="RUN STOPPED" if res.get("ok") else "STOP SENT",
            message=msg,
            level="cancelled" if res.get("ok") else "warning",
        )

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
    async def stream_agent_response(
        self,
        prompt: str,
        *,
        force_autonomous: bool = False,
        resume_run_id: Optional[str] = None,
        display_prompt: Optional[str] = None,
    ) -> None:
        """Streams assistant response over SSE from CoreService."""
        self.is_streaming = True
        self.current_stream_worker = get_current_worker()

        chat_log = self.query_one(ChatLog)
        header = self.query_one(HeaderBar)
        footer = self.query_one(FooterBar)
        hud = self.query_one(AgentStateHUD)
        input_well = self.query_one(InputWell)

        shown_prompt = display_prompt or prompt
        # 1. Mount User Turn Card and start this turn's execution graph
        chat_log.add_user_message(shown_prompt)
        self.exec_graph.start_turn(shown_prompt)
        self._refresh_graph_views()

        # 2. Update visual status
        header.status_label = "THINKING"
        footer.status = "THINKING"
        input_well.set_generating(True)
        hud.update_execution_state(
            step="n/a",
            tool_in_use="n/a",
            run_id=resume_run_id or "n/a",
            run_status="starting" if (force_autonomous or resume_run_id) else "n/a",
        )

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
        active_agent_id: str = "jarvis"
        is_mention_turn: bool = prompt.strip().startswith("@")

        try:
            async for event in stream_chat_events(
                message=prompt,
                base_url=self.core_url,
                client_id="terminal-ui",
                request_id=req_id,
                default_first_token_timeout=90.0,
                idle_gap_timeout=float(os.getenv("ZAINE_IDLE_TIMEOUT", "60.0")),
                force_autonomous=force_autonomous,
                resume_run_id=resume_run_id,
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
                    hud.update_execution_state(queue=f"pos #{pos} queued")

                # B. Running / Thinking
                elif ev_type == "running":
                    header.status_label = "THINKING"
                    footer.status = "THINKING"
                    hud.update_execution_state(queue="0 queued (1 active)")

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
                        if info.get("source") == "mention":
                            is_mention_turn = True
                        active_agent_id = str(info.get("agent_id") or active_agent_id)
                        header.agent_name, header.agent_color, header.agent_pinned = name, color, pinned
                        hud.update_agent(name, str(info.get("title", "")), str(info.get("reason", "")), color, pinned)
                        if active_assistant_card:
                            active_assistant_card.set_agent(name)

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
                        hud.update_execution_state(tool_in_use=tool_name or "n/a")
                        header.status_label = f"TOOL: {tool_name}"
                        footer.status = f"TOOL: {tool_name}"

                    elif stage == "plan_start":
                        info = data if isinstance(data, dict) else {}
                        hud.update_execution_state(
                            run_id=str(info.get("run_id") or hud.run_id),
                            step=f"0/{info.get('max_steps', '?')}",
                            run_status="planning",
                        )
                        header.status_label = "PLANNING"
                        footer.status = "PLANNING"

                    elif stage == "plan":
                        info = data if isinstance(data, dict) else {}
                        hud.update_execution_state(
                            run_id=str(info.get("run_id") or hud.run_id),
                            run_status="running",
                        )

                    elif stage == "resume":
                        info = data if isinstance(data, dict) else {}
                        hud.update_execution_state(
                            run_id=str(info.get("run_id") or resume_run_id or hud.run_id),
                            step=f"{info.get('start_step', '?')}/{info.get('max_steps', '?')}",
                            run_status="resumed",
                        )
                        header.status_label = f"RESUMING STEP {info.get('start_step', '?')}"
                        footer.status = header.status_label

                    elif stage == "step":
                        info = data if isinstance(data, dict) else {}
                        s_val = info.get("step", "?")
                        m_val = info.get("max_steps", "?")
                        hud.update_execution_state(
                            run_id=str(info.get("run_id") or hud.run_id),
                            step=f"{s_val}/{m_val}",
                            run_status=str(info.get("phase") or "running"),
                        )
                        header.status_label = f"STEP {s_val}/{m_val}"
                        footer.status = f"STEP {s_val}/{m_val}"

                    elif stage in ("circuit_breaker", "stopped_timeout", "stopped_max_steps", "cancelled", "privacy_blocked"):
                        hud.update_execution_state(run_status=stage, tool_in_use="n/a")

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
                        hud.update_execution_state(tool_in_use="n/a")
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
                        active_assistant_card.set_agent(header.agent_name)

                    active_assistant_card.append_token(content)
                    chat_log.scroll_end(animate=False)

                # E. Done Event
                elif ev_type == "done":
                    t_end = time.perf_counter()
                    total_dur = t_end - t_start
                    summary = self.exec_graph.summary()
                    th_str = f"{summary['tok_s']:.1f} tok/s" if summary["tok_s"] else "n/a"
                    hud.update_metrics(stream_active=False)
                    agent_run = event.get("agent_run")
                    if isinstance(agent_run, dict):
                        hud.update_execution_state(
                            run_id=str(agent_run.get("run_id") or hud.run_id),
                            step=f"{agent_run.get('steps_executed', '?')}/{agent_run.get('max_steps', '?')}",
                            tool_in_use="n/a",
                            run_status=str(agent_run.get("status") or "completed"),
                        )
                    else:
                        hud.update_execution_state(tool_in_use="n/a")

                    mode = event.get("mode")
                    if mode:
                        header.persona = mode.upper()
                        footer.persona = mode.upper()
                        hud.update_metrics(persona=mode.upper())

                    final_reply = ""
                    if active_assistant_card:
                        if event.get("reply"):
                            active_assistant_card.markdown_text = event.get("reply")
                        active_assistant_card.set_final(latency=f"{total_dur:.2f}s", throughput=th_str)
                        final_reply = active_assistant_card.markdown_text
                    elif event.get("reply"):
                        final_reply = event.get("reply", "")
                        # If completed without streaming token events (cached turn)
                        chat_log.add_assistant_message(
                            final_reply,
                            model=footer.model,
                            latency=f"{total_dur:.2f}s",
                            throughput=th_str
                        )
                    chat_log.scroll_end(animate=False)

                    # Trigger speech output if mentioned as @agentname or voice is explicitly toggled on
                    if (is_mention_turn or getattr(header, "voice_enabled", False)) and final_reply:
                        import voice
                        threading.Thread(
                            target=voice.speak_for_agent,
                            args=(final_reply, active_agent_id, True, is_mention_turn),
                            daemon=True
                        ).start()
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
                q_display = self._format_queue_display(self.system_facts.get("queue")) if self.system_facts.get("core_up") else "n/a"
                hud.update_execution_state(tool_in_use="n/a", queue=q_display)
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
