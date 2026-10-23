"""
Z.A.I.N.E TUI Persistent Status Footer Bar Widget (one visible row)
"""

from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text

from tui.theme import COLOR_EMERALD, COLOR_CYAN, COLOR_TEXT_MUTED, COLOR_TEXT_DIM
from tui.telemetry import get_cached_telemetry, get_tool_registry_count
from tui.widgets.header import status_badge


class FooterBar(Widget):
    """Bottom line: status, model, tools, RAM/VRAM from the cached telemetry snapshot, key hints.

    render() must stay cheap: it runs on every status change, so it never spawns nvidia-smi or psutil
    calls itself; the telemetry thread refreshes the snapshot every 2s.
    """

    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 1;
        background: #0b0f19;
        color: #64748b;
        padding: 0 1;
    }
    """

    status = reactive("WARMING UP")
    persona = reactive("JARVIS")
    model = reactive("n/a")
    session_id = reactive("n/a")
    voice_enabled = reactive(False)

    def __init__(self, **kwargs):
        super().__init__(id="footer-bar", **kwargs)

    def render(self) -> Text:
        t = Text()
        sep = (" │ ", COLOR_TEXT_DIM)
        badge, style = status_badge(self.status)
        t.append(badge, style=style)
        t.append(*sep)
        t.append(self.model, style=f"bold {COLOR_CYAN}")
        t.append(*sep)
        t.append(f"TOOLS {get_tool_registry_count()}", style=COLOR_TEXT_MUTED)
        snap = get_cached_telemetry()
        t.append(*sep)
        t.append(f"RAM {snap.ram_percent:.0f}%" if snap.ram != "n/a" else "RAM n/a", style=COLOR_TEXT_MUTED)
        t.append(*sep)
        t.append(f"VRAM {snap.vram_used_gb:.1f}/{snap.vram_total_gb:.1f}G" if snap.vram_available else "VRAM n/a",
                 style=COLOR_TEXT_MUTED)
        t.append(*sep)
        t.append("VOICE ON" if self.voice_enabled else "VOICE OFF", style=COLOR_EMERALD if self.voice_enabled else COLOR_TEXT_DIM)
        t.append("    F2 HUD · F3 GRAPH · Esc cancel · Ctrl+Q quit", style=COLOR_TEXT_DIM)
        return t
