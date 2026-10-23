"""
Z.A.I.N.E TUI Header Bar Widget
"""

from pathlib import Path
from typing import Tuple

from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text

from tui.theme import COLOR_EMERALD, COLOR_CYAN, COLOR_AMBER, COLOR_ROSE, COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM


def status_badge(label: str) -> Tuple[str, str]:
    """Glyph + style for a status label; shared by header and footer so both always agree."""
    s = (label or "").upper()
    if s == "READY":
        return "● READY", f"bold {COLOR_EMERALD}"
    if "OFFLINE" in s:
        return "○ CORE OFFLINE", f"bold {COLOR_ROSE}"
    if "WARMING" in s:
        return "⏳ WARMING UP", f"bold {COLOR_AMBER}"
    if "QUEUED" in s:
        return f"◌ {s}", f"bold {COLOR_AMBER}"
    if "APPROVAL" in s:
        return f"⛨ {s}", f"bold {COLOR_AMBER}"
    if s in ("APPROVED",):
        return "✓ APPROVED", f"bold {COLOR_EMERALD}"
    if s in ("DENIED", "NOT APPLIED"):
        return f"✗ {s}", f"bold {COLOR_ROSE}"
    if "THINKING" in s or "REASONING" in s:
        return f"◆ {s}", f"bold {COLOR_AMBER}"
    if "TOOL" in s:
        return f"⚙ {s}", f"bold {COLOR_CYAN}"
    if "STREAMING" in s:
        return "▶ STREAMING", f"bold {COLOR_CYAN}"
    return f"● {s}", COLOR_TEXT


class HeaderBar(Widget):
    """Top status line: brand, live status, view, routing tier, persona, voice, session."""

    DEFAULT_CSS = """
    HeaderBar {
        dock: top;
        height: 2;
        background: #0b0f19;
        border-bottom: solid #1e293b;
        padding: 0 1;
    }
    """

    persona = reactive("JARVIS")
    mode = reactive("—")
    view_mode = reactive("COMMAND")
    session_id = reactive("n/a")
    voice_enabled = reactive(False)
    status_label = reactive("WARMING UP")
    core_flags = reactive("")  # e.g. "DEMO · FAST" from the core's reported config

    def __init__(self, **kwargs):
        super().__init__(id="header-bar", **kwargs)
        self.cwd_name = Path.cwd().name

    def render(self) -> Text:
        t = Text()
        sep = ("  │  ", COLOR_TEXT_DIM)
        t.append("Z.A.I.N.E", style=f"bold {COLOR_EMERALD}")
        t.append(" NEURAL ", style=f"bold {COLOR_CYAN}")
        t.append("v3.5", style=COLOR_TEXT_MUTED)
        t.append(*sep)
        badge, style = status_badge(self.status_label)
        t.append(badge, style=style)
        if self.core_flags:
            t.append("  ")
            t.append(f"[{self.core_flags}]", style=f"bold {COLOR_AMBER}")
        t.append(*sep)
        view_col = COLOR_EMERALD if self.view_mode != "COMMAND" else COLOR_CYAN
        t.append(f"VIEW: {self.view_mode}", style=f"bold {view_col}")
        t.append(*sep)
        t.append("TIER: ", style=COLOR_TEXT_MUTED)
        t.append(self.mode, style=f"bold {COLOR_CYAN}")
        t.append(*sep)
        t.append(self.persona, style=f"bold {COLOR_EMERALD if self.persona == 'JARVIS' else COLOR_ROSE}")
        t.append(*sep)
        t.append("VOICE ON" if self.voice_enabled else "VOICE OFF",
                 style=COLOR_EMERALD if self.voice_enabled else COLOR_TEXT_DIM)
        t.append(*sep)
        t.append(f"~/{self.cwd_name}", style=COLOR_TEXT_MUTED)
        t.append(*sep)
        t.append(self.session_id, style=COLOR_TEXT_DIM)
        return t
