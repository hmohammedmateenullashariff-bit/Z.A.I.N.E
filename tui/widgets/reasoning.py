"""
Z.A.I.N.E TUI Collapsible Reasoning Block Widget (Violet #7928ca)
"""

from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text
from rich.panel import Panel

from tui.theme import COLOR_VIOLET, COLOR_PANEL, COLOR_BORDER, COLOR_TEXT_MUTED, COLOR_EMERALD


class ReasoningBlock(Widget):
    """Collapsible CoT reasoning block displayed before final answer."""

    DEFAULT_CSS = """
    ReasoningBlock {
        height: auto;
        margin: 1 0;
    }
    """

    is_collapsed = reactive(False)
    content = reactive("")
    is_complete = reactive(False)

    def __init__(self, reasoning_text: str = "", collapsed: bool = False, complete: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.content = reasoning_text
        self.is_collapsed = collapsed
        self.is_complete = complete

    def on_click(self) -> None:
        """Toggle collapse state on mouse click."""
        self.is_collapsed = not self.is_collapsed

    def toggle(self) -> None:
        """Toggle collapse state programmatically."""
        self.is_collapsed = not self.is_collapsed

    def stream_token(self, token: str) -> None:
        """Append streaming token live into deliberation body."""
        self.content += token
        self.refresh()

    def mark_complete(self) -> None:
        """Finalize reasoning state."""
        self.is_complete = True
        self.refresh()

    def render(self) -> Panel:
        glyph = "▶" if self.is_collapsed else "▼"
        state_label = "collapsed (click to expand)" if self.is_collapsed else "active (click to collapse)"

        title = Text()
        if self.is_complete:
            title.append("✓ [REASONING] ", style=f"bold {COLOR_EMERALD}")
            title.append(f"Reasoning complete · {state_label}", style=f"dim {COLOR_TEXT_MUTED}")
        else:
            title.append(f"{glyph} [REASONING] ", style=f"bold {COLOR_VIOLET}")
            title.append("Deliberating Chain-of-Thought...", style=f"dim {COLOR_TEXT_MUTED}")

        if self.is_collapsed:
            body = Text("... [deliberation tokens hidden] ...", style="italic #64748b")
        else:
            body = Text(self.content or "Analyzing context, safety boundaries, and user directives...", style="#c4b5fd")

        return Panel(
            body,
            title=title,
            title_align="left",
            border_style=COLOR_VIOLET,
            style=f"on {COLOR_PANEL}",
            padding=(0, 1),
        )
