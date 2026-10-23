"""
Z.A.I.N.E TUI Compact Tool Execution Line Widget (Cyan #00d2ff)
"""

from textual.widget import Widget
from rich.text import Text
from rich.panel import Panel

from tui.theme import (
    COLOR_CYAN, COLOR_SURFACE, COLOR_BORDER,
    COLOR_TEXT_MUTED, COLOR_TEXT_DIM, COLOR_EMERALD, COLOR_AMBER, COLOR_ROSE
)


class ToolLine(Widget):
    """Compact single-line tool invocation record."""

    DEFAULT_CSS = """
    ToolLine {
        height: auto;
        margin: 0 0 1 0;
    }
    """

    def __init__(self, tool_name: str, args_summary: str = "", duration_s: float = 0.0, status: str = "COMPLETED", **kwargs):
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.args_summary = args_summary
        self.duration_s = duration_s
        self.status = status

    def set_done(self, duration_s: float = 0.0, status: str = "COMPLETED") -> None:
        """Update tool execution outcome and duration."""
        self.duration_s = duration_s
        self.status = status
        self.refresh()

    def render(self) -> Panel:
        t = Text()
        t.append("⚙ [TOOL] ", style=f"bold {COLOR_CYAN}")
        t.append(f"{self.tool_name} ", style=f"bold #ffffff")

        if self.args_summary:
            t.append(f"({self.args_summary}) ", style=COLOR_TEXT_MUTED)

        t.append("· ", style=COLOR_TEXT_DIM)
        if self.duration_s > 0:
            t.append(f"{self.duration_s:.2f}s ", style=COLOR_TEXT_MUTED)

        if self.status == "COMPLETED":
            status_color = COLOR_EMERALD
        elif self.status in ("RUNNING", "AWAITING APPROVAL", "CANCELLED"):
            status_color = COLOR_AMBER
        elif self.status in ("FAILED", "BLOCKED"):
            status_color = COLOR_ROSE
        else:
            status_color = COLOR_CYAN

        t.append(f"· {self.status}", style=f"bold {status_color}")

        return Panel(
            t,
            border_style=status_color if self.status in ("FAILED", "BLOCKED") else COLOR_CYAN,
            style=f"on {COLOR_SURFACE}",
            padding=(0, 1)
        )
