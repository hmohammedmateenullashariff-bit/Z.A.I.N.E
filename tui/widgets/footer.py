"""
Z.A.I.N.E TUI Persistent Status Footer Bar Widget (Height 1)
"""

from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text

from tui.theme import COLOR_EMERALD, COLOR_CYAN, COLOR_TEXT_MUTED, COLOR_TEXT_DIM, COLOR_TEXT
from tui.telemetry import get_vram_info, get_system_hardware, get_tool_registry_count


class FooterBar(Widget):
    """Persistent single-line hardware and status footer."""

    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 1;
        background: #0b0f19;
        border-top: solid #1e293b;
        color: #64748b;
        padding: 0 1;
    }
    """

    status = reactive("READY")
    persona = reactive("JARVIS")
    model = reactive("zaine-reflex-7b")
    session_id = reactive("SES-1009-01")

    def __init__(self, **kwargs):
        super().__init__(id="footer-bar", **kwargs)

    def render(self) -> Text:
        t = Text()

        # Status badge
        if self.status == "READY":
            t.append("● READY ", style=f"bold {COLOR_EMERALD}")
        elif "QUEUED" in self.status:
            t.append(f"◌ {self.status} ", style="bold #f59e0b")
        elif "THINKING" in self.status:
            t.append("◆ THINKING ", style="bold #f59e0b")
        elif "STREAMING" in self.status:
            t.append("▶ STREAMING ", style=f"bold {COLOR_CYAN}")
        else:
            t.append(f"● {self.status} ", style=COLOR_TEXT)
        t.append("│ ", style=COLOR_TEXT_DIM)

        # Persona
        t.append(f"{self.persona} ", style=f"bold {COLOR_EMERALD}")
        t.append("│ ", style=COLOR_TEXT_DIM)

        # Model
        t.append(f"{self.model} ", style=f"bold {COLOR_CYAN}")
        t.append("│ ", style=COLOR_TEXT_DIM)

        # Voice
        t.append("VOICE: OFF ", style=COLOR_TEXT_DIM)
        t.append("│ ", style=COLOR_TEXT_DIM)

        # Tools
        tool_count = get_tool_registry_count()
        t.append(f"TOOLS: {tool_count} ", style=COLOR_TEXT_MUTED)
        t.append("│ ", style=COLOR_TEXT_DIM)

        # Hardware (100% Real)
        hw = get_system_hardware()
        vram = get_vram_info()
        t.append(f"RAM: {hw['ram_percent']} ", style=COLOR_TEXT_MUTED)
        t.append("│ ", style=COLOR_TEXT_DIM)

        if vram["available"]:
            t.append(f"VRAM: {vram['used_mb']/1024:.1f}/{vram['total_mb']/1024:.1f}GB ", style=COLOR_TEXT_MUTED)
        else:
            t.append("VRAM: n/a ", style=COLOR_TEXT_DIM)
        t.append("│ ", style=COLOR_TEXT_DIM)

        # Session
        t.append(self.session_id, style=f"dim {COLOR_TEXT_MUTED}")

        return t
