"""
Z.A.I.N.E TUI Agent State HUD Widget (right sidebar, F2 toggles)
Every value is real: persona/tier/model from routing events, token rates from Ollama's own
eval counters, a live execution trace, recent tools, vault stats and hardware telemetry.
"""

from typing import Any, Optional, List, Tuple
from textual.widget import Widget
from rich.text import Text

from tui.theme import (
    COLOR_EMERALD, COLOR_CYAN, COLOR_AMBER, COLOR_ROSE,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM, COLOR_BORDER,
)
from tui.telemetry import TelemetrySnapshot, get_cached_telemetry, get_tool_registry_count, get_throughput_sparkline
from tui.widgets.digraph import render_trace

LABEL_W = 12


def _section(t: Text, title: str, right: str = "", right_style: str = COLOR_TEXT_MUTED) -> None:
    t.append("\n")
    t.append(title, style=f"bold {COLOR_TEXT}")
    if right:
        t.append(f"  {right}", style=right_style)
    t.append("\n")


def _row(t: Text, label: str, value: str, style: str = COLOR_TEXT, max_w: Optional[int] = None) -> None:
    t.append(f"  {label:<{LABEL_W}}", style=COLOR_TEXT_MUTED)
    v_str = str(value)
    if max_w is not None and len(v_str) > max_w:
        v_str = v_str[: max(0, max_w - 1)] + "…"
    t.append(f"{v_str}\n", style=style)


def _bar(used: float, total: float, width: int = 14) -> str:
    frac = 0.0 if total <= 0 else max(0.0, min(1.0, used / total))
    filled = int(round(frac * width))
    return "█" * filled + "░" * (width - filled)


class AgentStateHUD(Widget):
    """Right-side real-time Agent State and Telemetry HUD."""

    DEFAULT_CSS = """
    AgentStateHUD {
        width: 42;
        min-width: 36;
        height: 1fr;
        background: #0b0f19;
        border-left: solid #1e293b;
        padding: 0 1;
        overflow-y: auto;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(id="hud-container", **kwargs)
        self.persona = "JARVIS"
        self.active_model = "n/a"
        self.model_tier = "n/a"
        self.voice_enabled = False
        self.last_ttft = "n/a"
        self.last_throughput = "n/a"
        self.stream_active = False
        self.eval_counts = "n/a"
        self.core_online: Optional[bool] = None
        self.telemetry_snapshot: Optional[TelemetrySnapshot] = None
        self.recent_tools: List[Tuple[str, str, str]] = []
        self.exec_graph: Optional[Any] = None
        # VisionQuest agent of the current/last turn
        self.agent_name = "n/a"
        self.agent_title = ""
        self.agent_reason = ""
        self.agent_color = COLOR_EMERALD
        self.agent_pinned = False

    def update_agent(self, name: str, title: str = "", reason: str = "", color: str = "", pinned: Optional[bool] = None) -> None:
        self.agent_name = name or "n/a"
        self.agent_title = title
        self.agent_reason = reason
        if color:
            self.agent_color = color
        if pinned is not None:
            self.agent_pinned = pinned
        self.refresh()

    def add_tool_run(self, tool_name: str, duration_s: float = 0.0, status: str = "COMPLETED") -> None:
        self.recent_tools.insert(0, (tool_name, f"{duration_s:.2f}s", status))
        self.recent_tools = self.recent_tools[:4]
        self.refresh()

    def update_telemetry(self, snapshot: TelemetrySnapshot) -> None:
        self.telemetry_snapshot = snapshot
        self.refresh()

    def update_metrics(
        self,
        persona: Optional[str] = None,
        model: Optional[str] = None,
        tier: Optional[str] = None,
        ttft: Optional[str] = None,
        throughput: Optional[str] = None,
        eval_counts: Optional[str] = None,
        stream_active: Optional[bool] = None,
    ) -> None:
        if persona:
            self.persona = persona
        if model:
            self.active_model = model
        if tier:
            self.model_tier = tier
        if ttft:
            self.last_ttft = ttft
        if throughput:
            self.last_throughput = throughput
        if eval_counts:
            self.eval_counts = eval_counts
        if stream_active is not None:
            self.stream_active = stream_active
        self.refresh()

    def render(self) -> Text:
        t = Text()
        snap = self.telemetry_snapshot or get_cached_telemetry()
        width = max(30, (self.size.width or 40) - 2)

        t.append("AGENT STATE HUD", style=f"bold {COLOR_CYAN}")
        if self.core_online is None:
            t.append("   ◌ CHECKING CORE\n", style=COLOR_TEXT_MUTED)
        elif self.core_online:
            t.append("   ● CORE LINKED\n", style=f"bold {COLOR_EMERALD}")
        else:
            t.append("   ○ CORE OFFLINE\n", style=f"bold {COLOR_ROSE}")
        t.append("─" * width + "\n", style=COLOR_BORDER)

        val_w = max(10, width - LABEL_W - 2)

        _section(t, "ACTIVE AGENT", "pinned" if self.agent_pinned else "auto-routed",
                 f"bold {COLOR_AMBER}" if self.agent_pinned else COLOR_TEXT_DIM)
        _row(t, "Agent", self.agent_name, f"bold {self.agent_color}", max_w=val_w)
        if self.agent_title:
            _row(t, "Role", self.agent_title, COLOR_TEXT, max_w=val_w)
        if self.agent_reason:
            reason_short = (self.agent_reason[: val_w - 1] + "…") if len(self.agent_reason) > val_w else self.agent_reason
            _row(t, "Why", reason_short, COLOR_TEXT_MUTED)
        consulted = getattr(self.exec_graph, "delegations", []) if self.exec_graph is not None else []
        if consulted:
            c_str = ", ".join(name for name, _ in consulted)
            if len(c_str) > val_w:
                c_str = c_str[: val_w - 1] + "…"
            _row(t, "Consulted", c_str, f"bold {COLOR_CYAN}")

        _section(t, "ACTIVE PERSONA")
        _row(t, "Persona", f"Z.A.I.N.E {self.persona}", f"bold {COLOR_EMERALD if self.persona == 'JARVIS' else COLOR_ROSE}")
        _row(t, "Tier", self.model_tier, COLOR_CYAN, max_w=val_w)
        _row(t, "Model", self.active_model, f"bold {COLOR_TEXT}", max_w=val_w)

        _section(t, "INFERENCE", "streaming" if self.stream_active else "idle",
                 f"bold {COLOR_CYAN}" if self.stream_active else COLOR_TEXT_DIM)
        _row(t, "First token", self.last_ttft, f"bold {COLOR_CYAN}")
        _row(t, "Throughput", f"{get_throughput_sparkline(length=8)} {self.last_throughput}", f"bold {COLOR_EMERALD}")
        _row(t, "Tokens", self.eval_counts, max_w=val_w)

        _section(t, "LIVE TRACE", "F3 full graph", COLOR_TEXT_DIM)
        t.append_text(render_trace(self.exec_graph, width, max_lines=7))

        _section(t, "RECENT TOOLS", f"{get_tool_registry_count()} available", COLOR_TEXT_DIM)
        if self.recent_tools:
            name_w = max(10, width - 20)
            for name, dur, st in self.recent_tools:
                color = COLOR_EMERALD if st == "COMPLETED" else (COLOR_ROSE if st in ("FAILED", "BLOCKED") else COLOR_AMBER)
                short = {"COMPLETED": "OK", "CANCELLED": "CANCEL"}.get(st, st)
                tool_disp = (name[: name_w - 1] + "…") if len(name) > name_w else name
                t.append(f"  ⚙ {tool_disp:<{name_w}}", style=COLOR_CYAN)
                t.append(f"{dur:>7} ", style=COLOR_TEXT_MUTED)
                t.append(f"{short}\n", style=f"bold {color}")
        else:
            t.append("  none yet\n", style=COLOR_TEXT_DIM)

        _section(t, "MEMORY")
        v_ok = snap.vault_status == "Connected"
        _row(t, "Vault", snap.vault_status, f"bold {COLOR_EMERALD if v_ok else COLOR_ROSE}")
        _row(t, "Notes", str(snap.vault_notes))
        _row(t, "Budget", f"{snap.context_budget} chars/turn")

        _section(t, "HARDWARE")
        _row(t, "CPU", f"{snap.cpu_sparkline} {snap.cpu}", COLOR_TEXT)
        _row(t, "RAM", snap.ram, COLOR_TEXT)
        if snap.vram_available:
            _row(t, "VRAM", f"{_bar(snap.vram_used_gb, snap.vram_total_gb)} {snap.vram_used_gb:.1f}/{snap.vram_total_gb:.1f}G",
                 f"bold {COLOR_CYAN}")
            temp = f" · {snap.gpu_temp_c:.0f}°C" if snap.gpu_temp_c > 0 else ""
            gpu_clean = snap.gpu_name.replace('NVIDIA GeForce ', '')
            gpu_str = f"{gpu_clean}{temp}"
            if len(gpu_str) > val_w:
                gpu_str = gpu_str[: val_w - 1] + "…"
            _row(t, "GPU", gpu_str, COLOR_TEXT_MUTED)
        else:
            _row(t, "VRAM", "n/a", COLOR_TEXT_DIM)
        return t
