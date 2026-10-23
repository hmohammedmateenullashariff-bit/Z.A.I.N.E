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
        latency: str = "n/a",
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
        background: #111622;
        border: round #f59e0b;
        border-title-color: #f59e0b;
        border-title-style: bold;
        padding: 0 1;
    }
    /* Containers default to height 1fr; inside an auto-height card that stretched the card past the
       viewport and pushed the command and buttons off-screen. */
    ApprovalCard Vertical, ApprovalCard Horizontal {
        height: auto;
    }
    ApprovalCard .approval-header {
        color: #f59e0b;
        text-style: bold;
    }
    ApprovalCard .approval-cmd {
        color: #00d2ff;
        text-style: bold;
        background: #030712;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    ApprovalCard .approval-meta {
        color: #64748b;
    }
    ApprovalCard .approval-actions {
        layout: horizontal;
        margin-top: 1;
    }
    ApprovalCard .approval-hint {
        width: auto;
        color: #64748b;
        padding: 1 0 0 1;
    }
    ApprovalCard Button {
        margin-right: 2;
        min-width: 16;
        height: 3;
    }
    ApprovalCard Button#btn-approve {
        background: #00f5a0;
        color: #030712;
        text-style: bold;
        border: tall #00f5a0;
    }
    ApprovalCard Button#btn-approve:hover {
        background: #50ffaf;
    }
    ApprovalCard Button#btn-deny {
        background: #0b0f19;
        color: #f0fdf4;
        border: tall #475569;
    }
    ApprovalCard Button#btn-deny:hover {
        color: #f43f5e;
        border: tall #f43f5e;
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
        risk_level: str = "",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.proposal_id = proposal_id
        self.command = command
        self.reason = reason
        self.tool_name = tool_name
        self.risk_level = risk_level
        self.timestamp = timestamp or datetime.now().strftime("%H:%M:%S")
        self.status = "PENDING"
        self.border_title = "⛨ EXECUTION GUARDRAIL INTERCEPT"

    def compose(self) -> ComposeResult:
        with Vertical():
            # Command, reason and tool name come from the model or tool arguments. Render them literally:
            # with markup on, "[Environment]::..." loses text and "[/]" raises MarkupError.
            risk = f" · risk {self.risk_level}" if self.risk_level else ""
            yield Static(f"Z.A.I.N.E requests permission to run {self.tool_name}{risk}", classes="approval-header", markup=False)
            yield Static(f"$ {self.command}" if self.command else f"$ {self.tool_name}", classes="approval-cmd", markup=False)
            if self.reason and self.reason != self.command:
                yield Static(f"Why: {self.reason}", classes="approval-meta", markup=False)
            yield Static(f"{self.proposal_id} · {self.timestamp} · the same request is on Telegram; first answer wins",
                         classes="approval-meta", markup=False)
            with Horizontal(classes="approval-actions", id="action-row"):
                yield Button(Text("[Y] Execute"), id="btn-approve", variant="success")
                yield Button(Text("[N] Reject"), id="btn-deny", variant="error")
                yield Static("or type y / n", classes="approval-hint", markup=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self.status != "PENDING":
            return
        if event.button.id == "btn-approve":
            self.post_message(self.Decision(self.proposal_id, "approve"))
        elif event.button.id == "btn-deny":
            self.post_message(self.Decision(self.proposal_id, "deny"))

    def set_resolved(self, decision: str, note: str = "") -> None:
        # Callers pass "approve"/"deny" or a final status such as APPROVED, DENIED, EXPIRED.
        status = decision.upper()
        self.status = {"APPROVE": "APPROVED", "DENY": "DENIED"}.get(status, status)
        try:
            row = self.query_one("#action-row")
            row.remove_children()
            if self.status == "APPROVED":
                badge = Static(f"✓ APPROVED by Operator [{self.proposal_id}] - {note or 'Executing...'}", classes="resolved-badge", markup=False)
                badge.styles.color = COLOR_EMERALD
            elif self.status == "DENIED":
                badge = Static(f"✗ DENIED by Operator [{self.proposal_id}] - {note or 'Action Aborted.'}", classes="resolved-badge", markup=False)
                badge.styles.color = COLOR_ROSE
            else:
                badge = Static(f"⌛ {self.status} [{self.proposal_id}] - {note or 'Action not executed.'}", classes="resolved-badge", markup=False)
                badge.styles.color = COLOR_AMBER
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

    WELCOME = (
        "Type a prompt or a /command. Live state (model, tokens, VRAM) is in the HUD on the right.\n"
        "F2 toggles the HUD · F3 opens the live execution graph · Esc cancels a reply · /help lists commands."
    )

    def compose(self) -> ComposeResult:
        yield NeuralBanner()
        # Real, static guidance only: no simulated turns or invented status claims.
        yield SystemCard(title="SESSION READY", message=self.WELCOME, level="info")

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
        tool_name: str = "execute_command",
        risk_level: str = "",
    ) -> ApprovalCard:
        """Add an interactive security approval card and scroll to bottom."""
        card = ApprovalCard(
            proposal_id=proposal_id,
            command=command,
            reason=reason,
            tool_name=tool_name,
            risk_level=risk_level,
        )
        self.mount(card)
        self.scroll_end(animate=False)
        return card

    def clear_history(self) -> None:
        """Clear chat messages and remount banner."""
        self.remove_children()
        self.mount(NeuralBanner())
        self.mount(SystemCard(title="SESSION READY", message=self.WELCOME, level="info"))
        self.scroll_home(animate=False)
