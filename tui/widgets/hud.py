"""
Z.A.I.N.E TUI Agent State HUD Widget (Right Sidebar ~30% Width)
Features real-time micro-sparklines (VRAM, CPU, Throughput),
non-blocking telemetry updates, and collapsible keybinding (F2).
"""

from typing import Optional, List, Tuple
from textual.widget import Widget
from rich.text import Text

from tui.theme import (
    COLOR_EMERALD, COLOR_CYAN, COLOR_VIOLET, COLOR_AMBER,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM, COLOR_BORDER, COLOR_PANEL, COLOR_ROSE
)
from tui.telemetry import (
    TelemetrySnapshot,
    get_cached_telemetry,
    get_vault_stats,
    get_tool_registry_count,
    get_throughput_sparkline,
)


class AgentStateHUD(Widget):
    """Right-side real-time Agent State and Telemetry HUD with micro-sparklines."""

    DEFAULT_CSS = """
    AgentStateHUD {
        width: 40;
        min-width: 34;
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
        self.active_model = "zaine-reflex-7b"
        self.model_tier = "Tier 0: Reflex"
        self.voice_enabled = False
        self.last_ttft = "n/a"
        self.last_throughput = "n/a"
        self.stream_active = False
        self.eval_counts = "n/a"
        self.telemetry_snapshot: Optional[TelemetrySnapshot] = None
        self.recent_tools: List[Tuple[str, str, str]] = [
            ("system_status", "0.03s", "COMPLETED"),
            ("search_vault", "0.04s", "COMPLETED"),
        ]

    def add_tool_run(self, tool_name: str, duration_s: float = 0.0, status: str = "COMPLETED") -> None:
        dur_str = f"{duration_s:.2f}s" if duration_s > 0 else "0.01s"
        self.recent_tools.insert(0, (tool_name, dur_str, status))
        self.recent_tools = self.recent_tools[:5]
        self.refresh()

    def update_telemetry(self, snapshot: TelemetrySnapshot) -> None:
        """Applies a non-blocking background telemetry snapshot."""
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
        """Updates cognitive and inference rate metrics."""
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

        # 1. Header
        t.append("AGENT STATE HUD ", style=f"bold {COLOR_CYAN}")
        t.append("● SYNCED\n", style=f"bold {COLOR_EMERALD}")
        t.append("─" * 36 + "\n", style=COLOR_BORDER)

        # 2. Agent State Section
        t.append("ACTIVE PERSONA\n", style=f"bold {COLOR_TEXT}")
        p_color = COLOR_EMERALD if self.persona == "JARVIS" else COLOR_ROSE
        t.append(f"  Z.A.I.N.E {self.persona}\n", style=f"bold {p_color}")
        t.append(f"  Cognitive Tier: {self.model_tier}\n", style=COLOR_TEXT_MUTED)
        t.append(f"  Model: {self.active_model}\n", style="bold #ffffff")
        v_state = "ON" if self.voice_enabled else "OFF (Standby)"
        v_color = COLOR_EMERALD if self.voice_enabled else COLOR_TEXT_DIM
        t.append(f"  Voice State: {v_state}\n\n", style=v_color)

        # 3. Inference & Stream Rate Section
        t.append("INFERENCE & STREAM RATE\n", style=f"bold {COLOR_TEXT}")
        t.append("  TTFT (First Token): ", style=COLOR_TEXT_MUTED)
        t.append(f"{self.last_ttft}\n", style=f"bold {COLOR_CYAN}")

        t.append("  Throughput: ", style=COLOR_TEXT_MUTED)
        tp_spark = get_throughput_sparkline(length=8)
        t.append(f"{tp_spark} ", style=f"bold {COLOR_EMERALD}")
        t.append(f"| {self.last_throughput}\n", style=f"bold {COLOR_TEXT}")

        eval_label = "Streaming Active" if self.stream_active else "Standby"
        eval_color = COLOR_EMERALD if self.stream_active else COLOR_TEXT_DIM
        t.append("  Stream State: ", style=COLOR_TEXT_MUTED)
        t.append(f"{eval_label}\n\n", style=f"bold {eval_color}")

        # 4. Memory Stack Section
        v_status = snap.vault_status if snap else "Connected"
        v_avail = (v_status == "Connected")
        v_notes = snap.vault_notes if snap else 0
        v_budget = snap.context_budget if snap else 2000
        t.append("MEMORY STACK CONTEXT\n", style=f"bold {COLOR_TEXT}")
        v_col = COLOR_EMERALD if v_avail else COLOR_ROSE
        t.append("  Obsidian Vault: ", style=COLOR_TEXT_MUTED)
        t.append(f"{v_status}\n", style=f"bold {v_col}")
        t.append("  Total Vault Notes: ", style=COLOR_TEXT_MUTED)
        t.append(f"{v_notes} files\n", style=f"bold {COLOR_TEXT}")
        t.append("  Context Budget: ", style=COLOR_TEXT_MUTED)
        t.append(f"{v_budget} chars\n\n", style=COLOR_TEXT_DIM)

        # 5. Tool Invocation Stack
        tool_count = get_tool_registry_count()
        t.append("TOOL STACK ", style=f"bold {COLOR_TEXT}")
        t.append(f"({tool_count} Units)\n", style=f"bold {COLOR_CYAN}")
        for tool_name, dur, st in self.recent_tools[:2]:
            t.append(f"  ⚙ {tool_name} ", style=COLOR_CYAN)
            t.append(f"· {dur} · {st}\n", style=COLOR_TEXT_MUTED)
        t.append("\n")

        # 6. Hardware Runtime Section with Live Sparklines
        t.append("HARDWARE TELEMETRY\n", style=f"bold {COLOR_TEXT}")

        # CPU with sparkline
        t.append("  CPU: ", style=COLOR_TEXT_MUTED)
        t.append(f"{snap.cpu} ", style=f"bold {COLOR_TEXT}")
        t.append(f"[{snap.cpu_sparkline}]\n", style=f"bold {COLOR_CYAN}")

        # RAM
        t.append("  System RAM: ", style=COLOR_TEXT_MUTED)
        t.append(f"{snap.ram}\n", style=COLOR_TEXT)

        # VRAM with micro-sparkline
        if snap.vram_available:
            t.append("  GPU VRAM: ", style=COLOR_TEXT_MUTED)
            t.append(f"{snap.vram_sparkline} ", style=f"bold {COLOR_CYAN}")
            t.append(f"| {snap.vram_used_gb:.1f} / {snap.vram_total_gb:.1f} GB\n", style=f"bold {COLOR_TEXT}")

            short_gpu = snap.gpu_name.replace("NVIDIA GeForce ", "")
            temp_str = f" ({snap.gpu_temp_c:.0f}°C)" if snap.gpu_temp_c > 0 else ""
            t.append("  GPU Engine: ", style=COLOR_TEXT_MUTED)
            t.append(f"{short_gpu}{temp_str}\n\n", style=COLOR_TEXT)
        else:
            t.append("  GPU VRAM: ", style=COLOR_TEXT_MUTED)
            t.append("Hardware inactive or N/A\n\n", style=COLOR_TEXT_DIM)

        # 7. Quick Orchestration Keymap
        t.append("QUICK ORCHESTRATIONS\n", style=f"bold {COLOR_TEXT}")
        t.append("  [F2]    Toggle HUD (Show/Hide)\n", style=COLOR_TEXT_MUTED)
        t.append("  [Esc]   Unfocus / Clear Input\n", style=COLOR_TEXT_MUTED)
        t.append("  [/help] Slash Command Reference\n", style=COLOR_TEXT_MUTED)
        t.append("  [Ctrl+C] Clean Graceful Exit\n", style=COLOR_TEXT_MUTED)

        return t
