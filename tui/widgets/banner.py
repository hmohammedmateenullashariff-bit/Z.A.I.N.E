"""
Z.A.I.N.E TUI Neural ASCII Banner Widget
"""

from textual.widget import Widget
from rich.text import Text
from rich.panel import Panel

from tui.theme import COLOR_EMERALD, COLOR_CYAN, COLOR_TEXT_MUTED, COLOR_TEXT_DIM, COLOR_BORDER, COLOR_SURFACE

ASCII_LOGO = r"""
 ███████╗ █████╗ ██╗███╗   ██╗███████╗    ███╗   ██╗███████╗██╗   ██╗██████╗  █████╗ ██╗     
 ╚══███╔╝██╔══██╗██║████╗  ██║██╔════╝    ████╗  ██║██╔════╝██║   ██║██╔══██╗██╔══██╗██║     
   ███╔╝ ███████║██║██╔██╗ ██║█████╗      ██╔██╗ ██║█████╗  ██║   ██║██████╔╝███████║██║     
  ███╔╝  ██╔══██║██║██║╚██╗██║██╔══╝      ██║╚██╗██║██╔══╝  ██║   ██║██╔══██╗██╔══██║██║     
 ███████╗██║  ██║██║██║ ╚████║███████╗    ██║ ╚████║███████╗╚██████╔╝██║  ██║██║  ██║███████╗
 ╚══════╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚══════╝    ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
""".strip("\n")


class NeuralBanner(Widget):
    """ASCII neural banner displayed at the top of the session log."""

    DEFAULT_CSS = """
    NeuralBanner {
        height: auto;
        margin: 1 0;
    }
    """

    def render(self) -> Panel:
        content = Text()
        content.append(ASCII_LOGO, style=f"bold {COLOR_EMERALD}")
        content.append("\n\n")

        # Telemetry metadata sub-line
        content.append(" CORE: ", style=COLOR_TEXT_DIM)
        content.append("v3.5.0-alpha ", style=f"bold {COLOR_CYAN}")
        content.append("· SUB-SYSTEM: ", style=COLOR_TEXT_DIM)
        content.append("Reflex-Core ", style=COLOR_TEXT_MUTED)
        content.append("· HOST: ", style=COLOR_TEXT_DIM)
        content.append("Local Workstation ", style=COLOR_TEXT_MUTED)
        content.append("· PROTOCOL: ", style=COLOR_TEXT_DIM)
        content.append("Jarvis-Guardian ", style=f"bold {COLOR_EMERALD}")

        return Panel(
            content,
            border_style=COLOR_BORDER,
            style=f"on {COLOR_SURFACE}",
            padding=(0, 1),
        )
