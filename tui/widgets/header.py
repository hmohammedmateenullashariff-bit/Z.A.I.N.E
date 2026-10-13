"""
Z.A.I.N.E TUI Header Bar Widget
"""

from pathlib import Path
from textual.widget import Widget
from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text

from tui.theme import COLOR_EMERALD, COLOR_CYAN, COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM


class HeaderBar(Widget):
    """Top-level telemetry and status header bar."""

    DEFAULT_CSS = """
    HeaderBar {
        dock: top;
        height: 3;
        background: #0b0f19;
        border-bottom: solid #1e293b;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }
    """

    persona = reactive("JARVIS")
    mode = reactive("COMPANION")
    view_mode = reactive("COMMAND")
    session_id = reactive("SES-1009-01")
    voice_enabled = reactive(False)
    status_label = reactive("READY")

    def __init__(self, **kwargs):
        super().__init__(id="header-bar", **kwargs)
        self.cwd_name = Path.cwd().name

    def render(self) -> Text:
        t = Text()

        # Left brand title
        t.append("Z.A.I.N.E ", style=f"bold {COLOR_EMERALD}")
        t.append("NEURAL ", style=f"bold {COLOR_CYAN}")
        t.append("CLI-v3.5 ", style=f"dim {COLOR_TEXT_MUTED}")

        t.append("│ ", style=COLOR_TEXT_DIM)
        if self.status_label == "READY":
            t.append("● READY ", style=f"bold {COLOR_EMERALD}")
        elif "THINKING" in self.status_label:
            t.append("◆ THINKING ", style="bold #f59e0b")
        elif "TOOL" in self.status_label:
            t.append("⚙ TOOL ", style=f"bold {COLOR_CYAN}")
        else:
            t.append(f"● {self.status_label} ", style=COLOR_TEXT)

        # Center CWD
        t.append("│ ", style=COLOR_TEXT_DIM)
        t.append(f"~/{self.cwd_name} ", style=COLOR_TEXT_MUTED)

        # Mode & View Workspace
        t.append("│ ", style=COLOR_TEXT_DIM)
        t.append(f"MODE: {self.mode} ", style=f"bold {COLOR_CYAN}")

        t.append("│ ", style=COLOR_TEXT_DIM)
        view_col = COLOR_EMERALD if "TOPOLOGY" in self.view_mode else COLOR_CYAN
        t.append(f"VIEW: {self.view_mode} ", style=f"bold {view_col}")

        # Right persona & session
        t.append("│ ", style=COLOR_TEXT_DIM)
        p_color = COLOR_EMERALD if self.persona == "JARVIS" else "#f43f5e"
        t.append(f"{self.persona} ", style=f"bold {p_color}")

        t.append("│ ", style=COLOR_TEXT_DIM)
        v_str = "VOICE: ON" if self.voice_enabled else "VOICE: OFF"
        v_col = COLOR_EMERALD if self.voice_enabled else COLOR_TEXT_DIM
        t.append(f"{v_str} ", style=v_col)

        t.append("│ ", style=COLOR_TEXT_DIM)
        t.append(self.session_id, style=f"dim {COLOR_TEXT_MUTED}")

        return t
