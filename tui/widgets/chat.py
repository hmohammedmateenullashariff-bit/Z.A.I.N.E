"""
Z.A.I.N.E TUI Chat Log and Message Turn Widgets
"""

from datetime import datetime
from textual.widget import Widget
from textual.message import Message
from textual.widgets import Button, Static
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.app import ComposeResult
from rich.text import Text
from rich.panel import Panel
from rich.markdown import Markdown as RichMarkdown

from tui.theme import (
    COLOR_EMERALD, COLOR_CYAN, COLOR_VIOLET, COLOR_AMBER, COLOR_ROSE,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM, COLOR_SURFACE, COLOR_BORDER
)
from tui.widgets.banner import NeuralBanner
from tui.widgets.reasoning import ReasoningBlock
from tui.widgets.tool_line import ToolLine


class UserTurnCard(Widget):
    """Visual card for user input turn."""

    DEFAULT_CSS = """
    UserTurnCard {
        width: 100%;
        max-width: 100%;
        height: auto;
        margin: 1 0;
    }
    """

    def __init__(self, text: str, timestamp: str = "", **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.timestamp = timestamp or datetime.now().strftime("%H:%M:%S")

    def render(self) -> Panel:
        title = Text()
        title.append("▶ USER ", style=f"bold {COLOR_EMERALD}")
        title.append(f"[{self.timestamp}]", style=f"dim {COLOR_TEXT_DIM}")

        body = Text(f"{self.text}", style=f"bold {COLOR_TEXT}")

        return Panel(
            body,
            title=title,
            title_align="left",
            border_style=COLOR_EMERALD,
            style=f"on {COLOR_SURFACE}",
            padding=(0, 1),
            expand=True,
        )


class AssistantTurnCard(Widget):
    """Visual card for assistant's markdown response."""

    DEFAULT_CSS = """
    AssistantTurnCard {
        width: 100%;
        max-width: 100%;
        height: auto;
        margin: 1 0;
    }
    """

    def __init__(
        self,
        markdown_text: str = "",
        model: str = "zaine-reflex-7b",
        latency: str = "0.42s",
        throughput: str = "",
        timestamp: str = "",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.markdown_text = markdown_text
        self.model = model
        self.latency = latency
        self.throughput = throughput
        self.timestamp = timestamp or datetime.now().strftime("%H:%M:%S")

    def append_token(self, token: str) -> None:
        """Appends a streamed token or sentence chunk to the response."""
        self.markdown_text += token
        self.refresh()

    def set_final(self, latency: str = "", throughput: str = "") -> None:
        """Sets final response metrics."""
        if latency:
            self.latency = latency
        if throughput:
            self.throughput = throughput
        self.refresh()

    def set_model(self, model: str) -> None:
        self.model = model
        self.refresh()

    def render(self) -> Panel:
        title = Text()
        title.append("Z.A.I.N.E ", style=f"bold {COLOR_CYAN}")
        meta = f"[{self.model} · {self.latency}"
        if self.throughput:
            meta += f" · {self.throughput}"
        meta += "] "
        title.append(meta, style=f"dim {COLOR_TEXT_MUTED}")
        title.append(f"[{self.timestamp}]", style=f"dim {COLOR_TEXT_DIM}")

        content_renderable = (
            RichMarkdown(self.markdown_text, code_theme="monokai", justify="left")
            if self.markdown_text
            else Text("▶ Generating response...", style=f"italic {COLOR_TEXT_MUTED}")
        )

        return Panel(
            content_renderable,
            title=title,
            title_align="left",
            border_style=COLOR_CYAN,
            style=f"on {COLOR_SURFACE}",
            padding=(0, 1),
            expand=True,
        )


class SystemCard(Widget):
    """Visual card for system events, warnings, errors, and cancellations."""

    DEFAULT_CSS = """
    SystemCard {
        height: auto;
        margin: 1 0;
    }
    """

    def __init__(self, title: str, message: str, level: str = "info", timestamp: str = "", **kwargs):
        super().__init__(**kwargs)
        self.title_text = title
        self.message = message
        self.level = level.lower()
        self.timestamp = timestamp or datetime.now().strftime("%H:%M:%S")

    def render(self) -> Panel:
        title = Text()
        if self.level == "error":
            title.append("✗ ", style=f"bold {COLOR_ROSE}")
            title.append(self.title_text, style=f"bold {COLOR_ROSE}")
            border = COLOR_ROSE
        elif self.level in ("warning", "timeout"):
            title.append("⚠ ", style=f"bold {COLOR_AMBER}")
            title.append(self.title_text, style=f"bold {COLOR_AMBER}")
            border = COLOR_AMBER
        elif self.level == "cancelled":
            title.append("⏹ ", style=f"bold {COLOR_AMBER}")
            title.append(self.title_text, style=f"bold {COLOR_AMBER}")
            border = COLOR_AMBER
        elif self.level == "success":
            title.append("✓ ", style=f"bold {COLOR_EMERALD}")
            title.append(self.title_text, style=f"bold {COLOR_EMERALD}")
            border = COLOR_EMERALD
        else:
            title.append("ℹ ", style=f"bold {COLOR_CYAN}")
            title.append(self.title_text, style=f"bold {COLOR_CYAN}")
            border = COLOR_CYAN

        title.append(f" [{self.timestamp}]", style=f"dim {COLOR_TEXT_DIM}")

        body = (
            RichMarkdown(self.message)
            if ("\n" in self.message or "**" in self.message or "`" in self.message)
            else Text(self.message, style=COLOR_TEXT)
        )

        return Panel(
            body,
            title=title,
            title_align="left",
            border_style=border,
            style=f"on {COLOR_SURFACE}",
            padding=(0, 1),
        )


class ApprovalCard(Widget):
    """Interactive card for security / human-in-the-loop approval."""

    DEFAULT_CSS = """
    ApprovalCard {
        height: auto;
        margin: 1 0;
        background: #0b0f19;
        border: heavy #f59e0b;
        padding: 0 1;
    }
    ApprovalCard .approval-header {
        color: #f59e0b;
        text-style: bold;
    }
    ApprovalCard .approval-cmd {
        color: #00d2ff;
        text-style: bold;
    }
    ApprovalCard .approval-meta {
        color: #64748b;
    }
    ApprovalCard .approval-actions {
        height: auto;
        layout: horizontal;
        margin-top: 1;
    }
    ApprovalCard Button {
        margin-right: 2;
        min-width: 14;
        height: 3;
    }
    ApprovalCard Button#btn-approve {
        background: #064e3b;
        color: #00f5a0;
        border: tall #00f5a0;
    }
    ApprovalCard Button#btn-approve:hover {
        background: #047857;
    }
    ApprovalCard Button#btn-deny {
        background: #4c0519;
        color: #f43f5e;
        border: tall #f43f5e;
    }
    ApprovalCard Button#btn-deny:hover {
        background: #9f1239;
    }
    ApprovalCard .resolved-badge {
        text-style: bold;
        margin-top: 1;
    }
    """

    class Decision(Message):
        def __init__(self, proposal_id: str, decision: str):
            super().__init__()
            self.proposal_id = proposal_id
            self.decision = decision

    def __init__(
        self,
        proposal_id: str,
        command: str = "",
        reason: str = "",
        tool_name: str = "execute_command",
        timestamp: str = "",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.proposal_id = proposal_id
        self.command = command
        self.reason = reason
        self.tool_name = tool_name
        self.timestamp = timestamp or datetime.now().strftime("%H:%M:%S")
        self.status = "PENDING"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"⚠️ SECURITY APPROVAL REQUIRED: {self.command or self.tool_name}", classes="approval-header")
            if self.command:
                yield Static(f"Payload: {self.command}", classes="approval-cmd")
            if self.reason:
                yield Static(f"Reason: {self.reason}", classes="approval-meta")
            yield Static(f"Proposal ID: [bold]{self.proposal_id}[/bold] · Tool: {self.tool_name} [{self.timestamp}]", classes="approval-meta")
            with Horizontal(classes="approval-actions", id="action-row"):
                yield Button("[Y] Approve", id="btn-approve", variant="success")
                yield Button("[N] Deny", id="btn-deny", variant="error")
                yield Static("Shortcuts: [bold][Y][/bold] / [bold][N][/bold] or type /approve or /deny", classes="approval-meta")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self.status != "PENDING":
            return
        if event.button.id == "btn-approve":
            self.post_message(self.Decision(self.proposal_id, "approve"))
        elif event.button.id == "btn-deny":
            self.post_message(self.Decision(self.proposal_id, "deny"))

    def set_resolved(self, decision: str, note: str = "") -> None:
        self.status = decision.upper()
        try:
            row = self.query_one("#action-row")
            row.remove_children()
            if self.status == "APPROVED":
                badge = Static(f"✓ APPROVED by Operator [{self.proposal_id}] - {note or 'Executing...'}", classes="resolved-badge")
                badge.styles.color = COLOR_EMERALD
            else:
                badge = Static(f"✗ DENIED by Operator [{self.proposal_id}] - {note or 'Action Aborted.'}", classes="resolved-badge")
                badge.styles.color = COLOR_ROSE
            row.mount(badge)
        except Exception:
            pass


class ChatLog(VerticalScroll):
    """Scrollable chat history container displaying banners and conversation turns."""

    DEFAULT_CSS = """
    ChatLog {
        width: 100%;
        height: 1fr;
        padding: 0 1;
        overflow-x: hidden;
        overflow-y: scroll;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(id="chat-log", **kwargs)

    def compose(self) -> ComposeResult:
        # Initial Neural Banner
        yield NeuralBanner()

        # Initial Welcome Demonstration Turn (Diagnostic / Architecture Briefing)
        yield UserTurnCard(text="system diagnostic status", timestamp="12:00:01")

        yield ReasoningBlock(
            reasoning_text=(
                "Deliberating query: 'system diagnostic status'\n"
                "1. Telemetry Subsystem: Inspecting neural cognitive router and model cluster...\n"
                "2. Hardware State: NVIDIA GeForce RTX 2050 (4GB VRAM active, thermal guard nominal).\n"
                "3. Verification: Upgraded Tier 0 Reflex (zaine-reflex-7b) and Tier 1 Coder (zaine-coder-7b) online.\n"
                "4. Synthesizing system health and architectural briefing card for operator."
            ),
            collapsed=False,
            complete=True
        )

        yield ToolLine(
            tool_name="system_status",
            args_summary="scope='hardware, models, memory'",
            duration_s=0.03,
            status="COMPLETED"
        )

        sample_response = (
            "**Z.A.I.N.E Neural Engine** is fully operational and synchronized in offline local-first companion mode.\n\n"
            "### Architecture Overview:\n"
            "- **Reflex Brain**: `zaine-reflex-7b` (4096 context, optimized low-latency quantized weights)\n"
            "- **Code Engine**: `zaine-coder-7b` (Ponytail ladder deliberation co-processor)\n"
            "- **Local Vault**: Persistent Markdown RAG & SQLite smart memories connected\n"
            "- **Hardware Telemetry**: NVIDIA GeForce RTX 2050 (4GB VRAM active, thermal guard nominal)\n\n"
            "*All cognitive operations execute 100% locally on your machine with zero external data transmission.*"
        )
        yield AssistantTurnCard(markdown_text=sample_response, latency="0.42s", throughput="38.5 tok/s", timestamp="12:00:02")

    def add_user_message(self, text: str) -> UserTurnCard:
        """Add a user message card and scroll to bottom."""
        card = UserTurnCard(text=text)
        self.mount(card)
        self.scroll_end(animate=False)
        return card

    def start_assistant_turn(self, model: str = "zaine-reflex-7b") -> AssistantTurnCard:
        """Mount an empty assistant response card for live token streaming."""
        card = AssistantTurnCard(markdown_text="", model=model, latency="streaming...")
        self.mount(card)
        self.scroll_end(animate=False)
        return card

    def add_assistant_message(self, markdown_text: str, model: str = "zaine-reflex-7b", latency: str = "n/a", throughput: str = "") -> AssistantTurnCard:
        """Add a complete assistant response card and scroll to bottom."""
        card = AssistantTurnCard(markdown_text=markdown_text, model=model, latency=latency, throughput=throughput)
        self.mount(card)
        self.scroll_end(animate=False)
        return card

    def start_reasoning_block(self, text: str = "") -> ReasoningBlock:
        """Mount an active reasoning block for live CoT streaming."""
        block = ReasoningBlock(reasoning_text=text, collapsed=False, complete=False)
        self.mount(block)
        self.scroll_end(animate=False)
        return block

    def start_tool_line(self, tool_name: str, args_summary: str = "") -> ToolLine:
        """Mount a compact tool execution line in RUNNING state."""
        line = ToolLine(tool_name=tool_name, args_summary=args_summary, duration_s=0.0, status="RUNNING")
        self.mount(line)
        self.scroll_end(animate=False)
        return line

    def add_tool_line(self, tool_name: str, args_summary: str = "", duration_s: float = 0.0, status: str = "COMPLETED") -> ToolLine:
        """Add a completed tool execution line and scroll to bottom."""
        line = ToolLine(tool_name=tool_name, args_summary=args_summary, duration_s=duration_s, status=status)
        self.mount(line)
        self.scroll_end(animate=False)
        return line

    def add_system_card(self, title: str, message: str, level: str = "info") -> SystemCard:
        """Add a system event, warning, timeout, or error card."""
        card = SystemCard(title=title, message=message, level=level)
        self.mount(card)
        self.scroll_end(animate=False)
        return card

    def add_approval_card(
        self,
        proposal_id: str,
        command: str = "",
        reason: str = "",
        tool_name: str = "execute_command"
    ) -> ApprovalCard:
        """Add an interactive security approval card and scroll to bottom."""
        card = ApprovalCard(
            proposal_id=proposal_id,
            command=command,
            reason=reason,
            tool_name=tool_name
        )
        self.mount(card)
        self.scroll_end(animate=False)
        return card

    def clear_history(self) -> None:
        """Clear chat messages and remount banner."""
        self.remove_children()
        self.mount(NeuralBanner())
        self.scroll_home(animate=False)
