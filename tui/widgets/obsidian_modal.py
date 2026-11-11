"""
tui/widgets/obsidian_modal.py
Interactive Obsidian Memory Digraph Modal Screen.
Renders an interactive neural network and memory digraph popup inspired by Obsidian's
graph view. Users can click/touch nodes to inspect live synaptic memory connections,
vault context, and real-time AI response propagation.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime

from rich.text import Text
from rich.panel import Panel
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal, Grid
from textual.widgets import Button, Static, Label
from textual import on

from tui.theme import (
    COLOR_EMERALD, COLOR_CYAN, COLOR_VIOLET_BRIGHT, COLOR_AMBER, COLOR_ROSE,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM, COLOR_SURFACE, COLOR_BORDER
)


class ObsidianMemoryModal(ModalScreen):
    """
    Mini popup modal displaying an interactive Obsidian-style cognitive memory digraph.
    Supports touch/click interaction on graph nodes to explore active memory associations,
    synaptic links, and live AI response propagation.
    """

    DEFAULT_CSS = """
    ObsidianMemoryModal {
        align: center middle;
        background: rgba(3, 7, 18, 0.85);
    }

    #obsidian-modal-dialog {
        width: 78;
        max-width: 95%;
        height: auto;
        max-height: 92%;
        background: #090e1c;
        border: heavy #00d2ff;
        padding: 0 1;
    }

    #modal-header {
        height: 2;
        layout: horizontal;
        border-bottom: solid #1e293b;
        margin-bottom: 1;
    }

    #modal-title {
        width: 1fr;
        color: #00d2ff;
        text-style: bold;
    }

    #modal-close-btn {
        width: 10;
        height: 1;
        min-width: 8;
        background: #1e293b;
        color: #f43f5e;
        border: none;
    }

    #modal-close-btn:hover {
        background: #f43f5e;
        color: #ffffff;
    }

    #graph-canvas {
        height: 13;
        background: #050811;
        border: solid #1e293b;
        padding: 0 1;
        margin-bottom: 1;
    }

    #node-buttons-row {
        height: 3;
        layout: horizontal;
        align: center middle;
        margin-bottom: 1;
    }

    #node-buttons-row Button {
        margin: 0 1;
        min-width: 12;
        height: 1;
        border: none;
        padding: 0 1;
        background: #1e293b;
        color: #94a3b8;
    }

    #node-buttons-row Button:hover {
        background: #334155;
        color: #00f5a0;
        text-style: bold;
    }

    #node-buttons-row Button.active-node {
        background: #00f5a0;
        color: #030712;
        text-style: bold;
    }

    #node-detail-panel {
        height: 8;
        background: #0c1222;
        border: solid #1e293b;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close Modal", show=False),
        Binding("f4", "dismiss", "Close Modal", show=False),
        Binding("1", "select_node('context')", "Context Node", show=False),
        Binding("2", "select_node('ai')", "AI Core", show=False),
        Binding("3", "select_node('vault')", "Vault Node", show=False),
        Binding("4", "select_node('agent')", "Agent Node", show=False),
        Binding("5", "select_node('tools')", "Tools Node", show=False),
    ]

    PULSE_FRAMES = [
        "● ──▶ ✦ ──▶ ◉",
        "○ ──▶ ● ──▶ ✦",
        "✦ ──▶ ○ ──▶ ●",
        "◉ ──▶ ✦ ──▶ ○",
    ]

    NODE_DETAILS = {
        "context": {
            "title": "🧠 CONVERSATION WORKING MEMORY",
            "type": "Episodic Buffer",
            "synapses": "14 connections active",
            "associations": [
                "• Recalls recent operator requests and task constraints",
                "• Context token utilization: ~320 tokens (lean budget)",
                "• Active multi-turn context retention: Stable"
            ]
        },
        "ai": {
            "title": "◉ SOLAR AI COGNITION CORE (ACTIVE)",
            "type": "Neural Inference Engine",
            "synapses": "Core synthesis hub (Reflex / Fast 3B)",
            "associations": [
                "• Deliberating within <think> tags prior to dispatch",
                "• Pinned in VRAM (keep_alive=-1) for immediate response",
                "• Streaming real-time tokens to TUI and audio synthesis"
            ]
        },
        "vault": {
            "title": "📁 OBSIDIAN MEMORY VAULT RAG",
            "type": "Semantic Knowledge Store",
            "synapses": "Connected to local Obsidian .md notes",
            "associations": [
                "• Architecture Blueprint & Codebase Map indexed",
                "• Dynamic learnings injected via continuous learning loop",
                "• YouTube Channel Growth & Persona notes active"
            ]
        },
        "agent": {
            "title": "🤖 ACTIVE MULTI-AGENT PERSONA",
            "type": "Orchestrator & Persona Router",
            "synapses": "Routing to @jarvis, @edith, @friday, @vision, @ultron",
            "associations": [
                "• Distinct neural timbre and speech rate bound to persona",
                "• HITL guardrail safety gates active on privileged ops",
                "• Subagent delegation depth configured (Max depth = 3)"
            ]
        },
        "tools": {
            "title": "⚙ TOOL EXECUTION CLUSTER",
            "type": "System & Developer Capabilities",
            "synapses": "120+ registered tools across 6 clusters",
            "associations": [
                "• GitHub Reverse Engineering & API extraction online",
                "• Video timeline editing & modern website scaffolding loaded",
                "• Hardware diagnostics & continuous thermal guard active"
            ]
        }
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active_node = "ai"
        self.pulse_idx = 0
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="obsidian-modal-dialog"):
            with Horizontal(id="modal-header"):
                yield Label("✦ OBSIDIAN MEMORY DIGRAPH · LIVE COGNITIVE GRAPH ✦", id="modal-title")
                yield Button("✕ CLOSE", id="modal-close-btn")
            yield Static(id="graph-canvas")
            with Horizontal(id="node-buttons-row"):
                yield Button("1. CONTEXT", id="btn-context", classes="")
                yield Button("2. AI CORE", id="btn-ai", classes="active-node")
                yield Button("3. VAULT", id="btn-vault", classes="")
                yield Button("4. AGENT", id="btn-agent", classes="")
                yield Button("5. TOOLS", id="btn-tools", classes="")
            yield Static(id="node-detail-panel")

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.25, self._tick)
        self._render_graph()
        self._render_details()

    def _tick(self) -> None:
        self.pulse_idx = (self.pulse_idx + 1) % len(self.PULSE_FRAMES)
        self._render_graph()

    def _render_graph(self) -> None:
        canvas = self.query_one("#graph-canvas", Static)
        p = self.PULSE_FRAMES[self.pulse_idx]
        t = Text()

        # Render ASCII Digraph matching Obsidian memory structure (compact <= 66 cols)
        t.append("  [1. 🧠 CONTEXT] ──────────┐\n", style=COLOR_EMERALD if self.active_node == "context" else COLOR_TEXT_MUTED)
        t.append("       │                   ▼\n", style=COLOR_BORDER)
        t.append(f"       │  {p}  ╭───────────────────────╮\n", style=COLOR_CYAN)
        t.append("       ├──────────────▶│ [2. ◉ ACTIVE AI CORE] │◀────── [3. 📁 VAULT]\n",
                 style=f"bold {COLOR_CYAN}" if self.active_node == "ai" else COLOR_TEXT)
        t.append("       │               ╰───────────┬───────────╯             ▲\n", style=COLOR_BORDER)
        t.append("       ▼                           │                         │\n", style=COLOR_BORDER)
        t.append("  [4. 🤖 AGENT]                    ▼                         │\n",
                 style=COLOR_VIOLET_BRIGHT if self.active_node == "agent" else COLOR_TEXT_MUTED)
        t.append("       │               [5. ⚙ TOOL CLUSTERS] ─────────────────┘\n",
                 style=COLOR_AMBER if self.active_node == "tools" else COLOR_TEXT_MUTED)
        t.append("       └───────────────────────────┘\n", style=COLOR_BORDER)
        t.append("  Tap/click any node above or press [1]-[5] to inspect associations.\n", style=COLOR_TEXT_DIM)
        t.no_wrap = True
        canvas.update(t)

    def _render_details(self) -> None:
        panel = self.query_one("#node-detail-panel", Static)
        data = self.NODE_DETAILS.get(self.active_node, self.NODE_DETAILS["ai"])
        t = Text()
        t.append(f" {data['title']}\n", style=f"bold {COLOR_EMERALD}")
        t.append(f" Type: {data['type']}  │  Synaptic Connectivity: {data['synapses']}\n", style=COLOR_TEXT_MUTED)
        t.append("─" * 70 + "\n", style=COLOR_BORDER)
        for line in data["associations"]:
            t.append(f" {line}\n", style=COLOR_TEXT)
        panel.update(t)

    @on(Button.Pressed, "#modal-close-btn")
    def on_close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#btn-context")
    def on_context(self) -> None:
        self.select_node("context")

    @on(Button.Pressed, "#btn-ai")
    def on_ai(self) -> None:
        self.select_node("ai")

    @on(Button.Pressed, "#btn-vault")
    def on_vault(self) -> None:
        self.select_node("vault")

    @on(Button.Pressed, "#btn-agent")
    def on_agent(self) -> None:
        self.select_node("agent")

    @on(Button.Pressed, "#btn-tools")
    def on_tools(self) -> None:
        self.select_node("tools")

    def select_node(self, node_key: str) -> None:
        self.active_node = node_key
        for k in ("context", "ai", "vault", "agent", "tools"):
            try:
                btn = self.query_one(f"#btn-{k}", Button)
                if k == node_key:
                    btn.add_class("active-node")
                else:
                    btn.remove_class("active-node")
            except Exception:
                pass
        self._render_graph()
        self._render_details()

    def action_select_node(self, node_key: str) -> None:
        self.select_node(node_key)
