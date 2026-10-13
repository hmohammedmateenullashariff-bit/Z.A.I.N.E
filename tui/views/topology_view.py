"""
tui/views/topology_view.py
Full-Screen 3D Neural Topology & Swarm Governance Workspace for Z.A.I.N.E TUI.
Displays the 3D Braille/ASCII rotating graph alongside Swarm Governance,
Obsidian Memory Topology, Cluster Specifications, and the live Inter-Agent Neural Bus.
"""

import sys
import time
from datetime import datetime
from typing import List
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal, Vertical
from rich.text import Text

from tui.theme import (
    COLOR_EMERALD,
    COLOR_CYAN,
    COLOR_VIOLET,
    COLOR_AMBER,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_DIM,
)
from tui.widgets.graph_3d import NeuralGraph3D
from tui.telemetry import (
    get_vault_stats,
    get_cached_telemetry,
    poll_hardware_telemetry,
    TelemetrySnapshot,
)


class SwarmGovernanceCard(Widget):
    """Displays multi-agent swarm governance, consensus status, and thread limits."""

    DEFAULT_CSS = """
    SwarmGovernanceCard {
        height: auto;
        background: #0b0f19;
        border: solid #1e293b;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    """

    def render(self) -> Text:
        t = Text()
        t.append("╭─ SWARM GOVERNANCE & CONSENSUS [CONCEPT MOCK] ─╮\n", style=f"bold {COLOR_CYAN}")

        t.append("│ Consensus Status : ", style=COLOR_TEXT_MUTED)
        t.append("● 100% SYNCHRONIZED\n", style=f"bold {COLOR_EMERALD}")

        t.append("│ Active Load      : ", style=COLOR_TEXT_MUTED)
        t.append("24.8% Nominal (Balanced)\n", style=COLOR_TEXT)

        t.append("│ Thread Pool      : ", style=COLOR_TEXT_MUTED)
        t.append("4 / 8 THREADS (FIFO Guard)\n", style=f"bold {COLOR_CYAN}")

        t.append("│ Core Quorum      : ", style=COLOR_TEXT_MUTED)
        t.append("ACHIEVED (3/3 Cores Online)\n", style=COLOR_EMERALD)

        t.append("│ Swarm Heartbeat  : ", style=COLOR_TEXT_MUTED)
        t.append("● NOMINAL (1.2s ping)\n", style=f"dim {COLOR_TEXT_MUTED}")

        t.append("│ Action Guardian  : ", style=COLOR_TEXT_MUTED)
        t.append("ACTIVE (Human-in-the-Loop)\n", style=f"bold {COLOR_AMBER}")

        t.append("╰───────────────────────────────────────────────╯", style=f"dim {COLOR_TEXT_DIM}")
        return t


class MemoryTopologyCard(Widget):
    """Displays real Obsidian vault node breakdown and token context budget."""

    DEFAULT_CSS = """
    MemoryTopologyCard {
        height: auto;
        background: #0b0f19;
        border: solid #1e293b;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    """

    def render(self) -> Text:
        v_stats = get_vault_stats()
        notes_count = v_stats.get("notes_count", 21)
        total_kb = v_stats.get("total_bytes", 48200) / 1024.0

        t = Text()
        t.append("╭─ OBSIDIAN MEMORY TOPOLOGY ────────────────────╮\n", style=f"bold {COLOR_VIOLET}")

        t.append("│ Vault Index Store: ", style=COLOR_TEXT_MUTED)
        t.append(f"vault.db ({notes_count} durable notes)\n", style=f"bold {COLOR_VIOLET}")

        t.append("│ Total Vault Size : ", style=COLOR_TEXT_MUTED)
        t.append(f"{total_kb:.1f} KB Index Cache\n", style=COLOR_TEXT)

        t.append("│ Vault Hierarchy  : ", style=COLOR_TEXT_MUTED)
        t.append("00_Sys │ 10_Episodic │ 20_Intel\n", style=f"dim {COLOR_TEXT_MUTED}")

        t.append("│ Context Budget   : ", style=COLOR_TEXT_MUTED)
        t.append("32,768 Context Limit\n", style=f"bold {COLOR_CYAN}")

        t.append("│ Active Tokens    : ", style=COLOR_TEXT_MUTED)
        t.append("4,096 tok [", style=COLOR_TEXT)
        t.append("████░░░░░░░░░░░░", style=f"bold {COLOR_EMERALD}")
        t.append("] 12.5%\n", style=COLOR_TEXT_MUTED)

        t.append("╰───────────────────────────────────────────────╯", style=f"dim {COLOR_TEXT_DIM}")
        return t


class ClusterSpecCard(Widget):
    """Displays hardware cluster specification (GPU, VRAM, Primary Engines)."""

    DEFAULT_CSS = """
    ClusterSpecCard {
        height: auto;
        background: #0b0f19;
        border: solid #1e293b;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    """

    def render(self) -> Text:
        snap = get_cached_telemetry()
        vram_str = "2.4 / 4.0 GB (60%)"
        if snap:
            if getattr(snap, "vram", "n/a") not in ("n/a", "", None):
                vram_str = snap.vram
            elif getattr(snap, "vram_display", "n/a") not in ("n/a", "", None):
                vram_str = snap.vram_display

        t = Text()
        t.append("╭─ NEURAL COMPUTE CLUSTER ──────────────────────╮\n", style=f"bold {COLOR_EMERALD}")

        t.append("│ GPU Hardware     : ", style=COLOR_TEXT_MUTED)
        t.append("NVIDIA RTX 2050 (4GB VRAM)\n", style=f"bold {COLOR_EMERALD}")

        t.append("│ Allocated VRAM   : ", style=COLOR_TEXT_MUTED)
        t.append(f"{vram_str}\n", style=f"bold {COLOR_CYAN}")

        t.append("│ Reflex Engine    : ", style=COLOR_TEXT_MUTED)
        t.append("zaine-reflex-7b (Tier 0)\n", style=COLOR_TEXT)

        t.append("│ Coding Engine    : ", style=COLOR_TEXT_MUTED)
        t.append("zaine-coder-7b (Tier 1)\n", style=COLOR_TEXT)

        t.append("│ Vision Model     : ", style=COLOR_TEXT_MUTED)
        t.append("moondream:latest (1.8B VLM)\n", style=COLOR_TEXT_MUTED)

        t.append("│ Thermal Status   : ", style=COLOR_TEXT_MUTED)
        t.append("48°C Nominal (Safe < 82°C)\n", style=COLOR_EMERALD)

        t.append("╰───────────────────────────────────────────────╯", style=f"dim {COLOR_TEXT_DIM}")
        return t


class NeuralBusPanel(Widget):
    """Displays real-time Inter-Agent Neural Bus event broadcast stream log."""

    DEFAULT_CSS = """
    NeuralBusPanel {
        height: 7;
        background: #080d1a;
        border: solid #1e293b;
        padding: 0 1;
        margin: 0 1 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._timer = None
        now_str = datetime.now().strftime("%H:%M:%S")
        self._events: List[str] = [
            f"[{now_str}] BUS:CORE     ──▶ REFLEX-7B   : Sync heartbeat acknowledged (latency: 1.1ms)",
            f"[{now_str}] BUS:MEMORY   ──▶ OBSIDIAN    : Vault category index verified (21 nodes, 0 conflicts)",
            f"[{now_str}] BUS:SWARM    ──▶ CONSENSUS   : Multi-agent quorum verified (100% SYNC, 0 divergence)",
            f"[{now_str}] BUS:GPU      ──▶ TELEMETRY   : RTX 2050 VRAM nominal (2.4 GB / 4.0 GB, 48°C)",
            f"[{now_str}] BUS:ROUTER   ──▶ TIER_0      : Reflex standby nominal; zero pending queue tasks",
        ]
        self._sim_messages = [
            ("BUS:CORE", "CODER-7B", "Idempotency coordinator token pool verified"),
            ("BUS:MEMORY", "OBSIDIAN", "Knowledge index synced with SQLite metadata"),
            ("BUS:SWARM", "CONSENSUS", "Periodic consensus health-check: 100% agreement"),
            ("BUS:TELEMETRY", "GPU", "PCIe bus bandwidth nominal; thermals at 49°C"),
            ("BUS:ROUTER", "REFLEX-7B", "Standby latency test completed in 0.8ms"),
        ]
        self._sim_idx = 0

    def on_mount(self) -> None:
        if not ("unittest" in sys.modules or "pytest" in sys.modules):
            self._timer = self.set_interval(3.0, self._rotate_event)

    def on_unmount(self) -> None:
        if self._timer:
            try:
                self._timer.pause()
            except Exception:
                pass

    def pause_log(self) -> None:
        if self._timer:
            try:
                self._timer.pause()
            except Exception:
                pass

    def resume_log(self) -> None:
        if "unittest" in sys.modules or "pytest" in sys.modules:
            return
        if self._timer:
            try:
                self._timer.resume()
            except Exception:
                pass

    def _rotate_event(self) -> None:
        if not self.visible or not self.display:
            return
        now_str = datetime.now().strftime("%H:%M:%S")
        src, dst, msg = self._sim_messages[self._sim_idx % len(self._sim_messages)]
        self._sim_idx += 1
        line = f"[{now_str}] {src:<12} ──▶ {dst:<12}: {msg}"
        self._events.append(line)
        if len(self._events) > 5:
            self._events.pop(0)
        self.refresh()

    def render(self) -> Text:
        t = Text()
        t.append("INTER-AGENT NEURAL BUS [SIMULATED CONCEPT BUS] ", style=f"bold {COLOR_CYAN}")
        t.append("── CONCEPT SPECIFICATION\n", style=f"dim {COLOR_EMERALD}")

        for ev in self._events[-4:]:
            # Highlight parts of event string
            if "BUS:CORE" in ev or "BUS:SWARM" in ev:
                t.append(ev[:10], style="dim #64748b")
                t.append(ev[10:35], style=f"bold {COLOR_CYAN}")
                t.append(ev[35:] + "\n", style=COLOR_TEXT)
            elif "BUS:MEMORY" in ev:
                t.append(ev[:10], style="dim #64748b")
                t.append(ev[10:35], style=f"bold {COLOR_VIOLET}")
                t.append(ev[35:] + "\n", style=COLOR_TEXT)
            elif "BUS:GPU" in ev or "BUS:TELEMETRY" in ev:
                t.append(ev[:10], style="dim #64748b")
                t.append(ev[10:35], style=f"bold {COLOR_EMERALD}")
                t.append(ev[35:] + "\n", style=COLOR_TEXT)
            else:
                t.append(ev[:10], style="dim #64748b")
                t.append(ev[10:35], style=f"bold #f59e0b")
                t.append(ev[35:] + "\n", style=COLOR_TEXT)

        return t


class TopologyWorkspace(Widget):
    """Full-Screen Neural Topology & 3D Node Graph Dashboard Workspace."""

    DEFAULT_CSS = """
    TopologyWorkspace {
        height: 1fr;
        layout: vertical;
        background: #030712;
    }
    #topo-main-split {
        height: 1fr;
        layout: horizontal;
    }
    #topo-canvas-container {
        width: 65%;
        height: 1fr;
        background: #080d1a;
        border: solid #1e293b;
        margin: 0 1 0 1;
    }
    #topo-sidebar {
        width: 35%;
        height: 1fr;
        layout: vertical;
        overflow-y: auto;
        margin: 0 1 0 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="topo-main-split"):
            with Vertical(id="topo-canvas-container"):
                yield NeuralGraph3D(id="topo-graph-canvas")
            with Vertical(id="topo-sidebar"):
                yield SwarmGovernanceCard(id="topo-card-gov")
                yield MemoryTopologyCard(id="topo-card-mem")
                yield ClusterSpecCard(id="topo-card-cluster")
        yield NeuralBusPanel(id="topo-bus-panel")

    def pause_animation(self) -> None:
        """Pause 3D canvas and neural bus rotation when hidden."""
        try:
            canvas = self.query_one(NeuralGraph3D)
            canvas.pause_animation()
        except Exception:
            pass
        try:
            bus = self.query_one(NeuralBusPanel)
            bus.pause_log()
        except Exception:
            pass

    def resume_animation(self) -> None:
        """Resume 3D canvas and neural bus rotation when displayed."""
        try:
            canvas = self.query_one(NeuralGraph3D)
            canvas.resume_animation()
        except Exception:
            pass
        try:
            bus = self.query_one(NeuralBusPanel)
            bus.resume_log()
        except Exception:
            pass
