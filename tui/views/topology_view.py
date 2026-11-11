"""
tui/views/topology_view.py
F3 graph workspace. Every value shown here is real:
  [1] Execution DAG  - live digraph of the current turn, built from core_service SSE events
  [2] System         - topology from core_service, Ollama, tool clusters, vault and Telegram
  [3] Orbit 3D       - the same system graph on the rotating braille orbit
plus a turn summary, a system status card and the raw event stream that built the DAG.
"""

from typing import Any, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import ContentSwitcher, Static

from tui.theme import (
    COLOR_EMERALD, COLOR_CYAN, COLOR_VIOLET_BRIGHT, COLOR_AMBER, COLOR_ROSE,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM,
)
from tui.widgets.digraph import DigraphCanvas, SunDigraphCanvas
from tui.widgets.graph_3d import NeuralGraph3D

MODES = [("exec", "1", "EXECUTION DAG"), ("system", "2", "SYSTEM TOPOLOGY"), ("orbit", "3", "ORBIT 3D"), ("sun", "4", "SUN DIGRAPH")]

CHANNEL_COLORS = {
    "USER": COLOR_EMERALD, "ROUTER": COLOR_VIOLET_BRIGHT, "OLLAMA": COLOR_CYAN, "TOOL": COLOR_AMBER,
    "GUARD": COLOR_AMBER, "REPLY": COLOR_EMERALD, "ERROR": COLOR_ROSE, "CANCEL": COLOR_AMBER,
    "COORD": COLOR_TEXT_MUTED, "CORE": COLOR_TEXT_MUTED,
}


def _kv(t: Text, key: str, value: str, style: str = COLOR_TEXT, max_val_w: Optional[int] = None) -> None:
    t.append(f" {key:<14}", style=COLOR_TEXT_MUTED)
    v_str = str(value)
    if max_val_w is not None and len(v_str) > max_val_w:
        v_str = v_str[: max(0, max_val_w - 1)] + "…"
    t.append(f"{v_str}\n", style=style)


class GraphTabs(Static):
    """Mode selector line; the active mode is highlighted."""

    DEFAULT_CSS = """
    GraphTabs { height: 1; background: #0b0f19; padding: 0 1; }
    """

    def show(self, active: str) -> None:
        t = Text()
        for mode, key, label in MODES:
            if mode == active:
                t.append(f" [{key}] {label} ", style=f"bold #030712 on {COLOR_EMERALD}")
            else:
                t.append(f" [{key}] {label} ", style=COLOR_TEXT_MUTED)
            t.append(" ")
        t.append("  │ ", style=COLOR_TEXT_DIM)
        for glyph, color, word in (("◆", COLOR_CYAN, "running"), ("●", COLOR_EMERALD, "ok"),
                                   ("◌", COLOR_AMBER, "waiting"), ("⊘", COLOR_ROSE, "blocked/failed")):
            t.append(f"{glyph} {word}  ", style=color)
        t.append("│ [F3] back", style=COLOR_TEXT_DIM)
        self.update(t)


class TurnSummaryCard(Widget):
    """Numbers for the current/last turn, all taken from the execution graph."""

    DEFAULT_CSS = """
    TurnSummaryCard { height: auto; background: #0b0f19; border: solid #1e293b; padding: 0 1; margin: 0 0 1 0; }
    """

    graph: Optional[Any] = None

    def render(self) -> Text:
        t = Text()
        t.append("TURN SUMMARY\n", style=f"bold {COLOR_CYAN}")
        g = self.graph
        if g is None or g.is_empty:
            t.append(" No turn yet. Press F3 for the command view and send a prompt.\n", style=f"italic {COLOR_TEXT_MUTED}")
            return t
        s = g.summary()
        state = ("RUNNING", COLOR_CYAN) if s["active"] else ("DONE", COLOR_EMERALD)
        if not s["active"] and any(n.kind == "error" for n in g.nodes.values()):
            state = ("HALTED", COLOR_ROSE)
        room = max(10, (self.size.width or 44) - 18)
        _kv(t, "Turn", f"#{s['turn']}  {state[0]}", f"bold {state[1]}", max_val_w=room)
        _kv(t, "Prompt", s["prompt"], max_val_w=room)
        _kv(t, "Agent", s.get("agent", "n/a"), f"bold {COLOR_VIOLET_BRIGHT}", max_val_w=room)
        if s.get("delegations"):
            del_str = ", ".join(f"{n} ({o})" for n, o in s["delegations"])
            _kv(t, "Consulted", del_str, f"bold {COLOR_CYAN}", max_val_w=room)
        _kv(t, "Tier / model", f"{s['tier']} · {s['model']}", COLOR_TEXT, max_val_w=room)
        _kv(t, "LLM hops", str(s["hops"]), max_val_w=room)
        _kv(t, "Tokens out", f"{s['tokens']}" + (f" @ {s['tok_s']:.1f} tok/s" if s["tok_s"] else ""), f"bold {COLOR_CYAN}", max_val_w=room)
        failed = f" ({s['tools_failed']} blocked/failed)" if s["tools_failed"] else ""
        _kv(t, "Tool calls", f"{s['tools']}{failed}", COLOR_AMBER if s["tools_failed"] else COLOR_TEXT, max_val_w=room)
        if s["approvals"]:
            for pid, outcome in s["approvals"]:
                color = COLOR_EMERALD if outcome == "APPROVED" else (COLOR_AMBER if outcome == "PENDING" else COLOR_ROSE)
                _kv(t, "Approval", f"{pid} {outcome}", f"bold {color}", max_val_w=room)
        else:
            _kv(t, "Approvals", "none", max_val_w=room)
        _kv(t, "Elapsed", f"{s['elapsed_s']:.1f}s", max_val_w=room)
        return t


class SystemStatusCard(Widget):
    """Live facts gathered with the system topology (core, models in VRAM, approvals, Telegram)."""

    DEFAULT_CSS = """
    SystemStatusCard { height: auto; background: #0b0f19; border: solid #1e293b; padding: 0 1; margin: 0 0 1 0; }
    """

    facts: Optional[dict] = None

    def render(self) -> Text:
        t = Text()
        t.append("SYSTEM STATUS\n", style=f"bold {COLOR_EMERALD}")
        f = self.facts
        if not f:
            t.append(" Collecting…\n", style=f"italic {COLOR_TEXT_MUTED}")
            return t
        room = max(10, (self.size.width or 42) - 18)
        cs = f.get("core_status") or {}
        if f.get("core_up"):
            state = "warming" if cs.get("warming") else ("ready" if cs.get("model_loaded") else "no model loaded")
            _kv(t, "Core", f"online :{cs.get('port', '?')} · {state}", f"bold {COLOR_EMERALD}", max_val_w=room)
            _kv(t, "Persona", str(cs.get("mode", "n/a")).upper(), max_val_w=room)
            cfg = cs.get("config") or {}
            if cfg:
                mode = ", ".join(n for n, on in (("demo", cfg.get("demo")), ("fast 3B", cfg.get("fast"))) if on) or "standard"
                _kv(t, "Mode", f"{mode} · ctx {cfg.get('num_ctx', '?')}", f"bold {COLOR_AMBER}" if cfg.get("demo") else COLOR_TEXT, max_val_w=room)
                ws = str(cfg.get("workspace", "")).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
                _kv(t, "Workspace", ws or "n/a", max_val_w=room)
        else:
            _kv(t, "Core", "offline", f"bold {COLOR_ROSE}", max_val_w=room)
        _kv(t, "Ollama", "online" if f.get("ollama_up") else "offline",
            COLOR_EMERALD if f.get("ollama_up") else COLOR_ROSE, max_val_w=room)
        loaded = f.get("loaded_models") or []
        if loaded:
            for name, vram in loaded:
                _kv(t, "In VRAM", f"{name} {vram:.1f}G", f"bold {COLOR_CYAN}", max_val_w=room)
        else:
            _kv(t, "In VRAM", "none", max_val_w=room)
        pending = f.get("pending_approvals")
        _kv(t, "Approvals", "n/a" if pending is None else f"{pending} pending",
            COLOR_AMBER if pending else COLOR_TEXT, max_val_w=room)
        _kv(t, "Telegram", "poller online" if f.get("telegram_online") else "poller off",
            COLOR_EMERALD if f.get("telegram_online") else COLOR_TEXT_MUTED, max_val_w=room)
        return t


class EventStreamPanel(Widget):
    """The real events (SSE + derived) that built the execution DAG, newest last."""

    DEFAULT_CSS = """
    EventStreamPanel { height: 1fr; background: #080d1a; border: solid #1e293b; padding: 0 1; }
    """

    graph: Optional[Any] = None

    def render(self) -> Text:
        t = Text()
        t.append("EVENT STREAM ", style=f"bold {COLOR_CYAN}")
        t.append("· live from /api/chat/stream\n", style=COLOR_TEXT_DIM)
        events = list(self.graph.events) if self.graph is not None else []
        if not events:
            t.append(" Waiting for the first turn…", style=f"italic {COLOR_TEXT_MUTED}")
            return t
        width = max(20, (self.size.width or 100) - 26)
        rows = (self.size.height - 3) if self.size.height else 8
        for stamp, channel, text in events[-max(1, rows):]:
            t.append(f"[{stamp}] ", style=COLOR_TEXT_DIM)
            t.append(f"{channel:<7}", style=f"bold {CHANNEL_COLORS.get(channel, COLOR_TEXT)}")
            t.append((text if len(text) <= width else text[: width - 1] + "…") + "\n", style=COLOR_TEXT)
        return t


class TopologyWorkspace(Widget):
    """F3 workspace: live execution digraph, real system topology and orbit view."""

    DEFAULT_CSS = """
    TopologyWorkspace { height: 1fr; layout: vertical; background: #030712; }
    #topo-canvas-container { width: 1fr; height: 1fr; background: #080d1a; border: solid #1e293b; margin: 0 1; }
    #topo-switcher { height: 1fr; }
    #topo-bottom { height: 14; layout: horizontal; margin: 0 1; }
    #topo-turn { width: 1fr; min-width: 32; max-width: 46; height: 1fr; margin: 0 1 0 0; }
    #topo-system { width: 1fr; min-width: 30; max-width: 42; height: 1fr; margin: 0 1 0 0; }
    #topo-bus-panel { width: 2fr; min-width: 24; height: 1fr; margin: 0; }
    """

    BINDINGS = [
        Binding("1", "show_mode('exec')", "Execution DAG", show=False),
        Binding("2", "show_mode('system')", "System topology", show=False),
        Binding("3", "show_mode('orbit')", "Orbit 3D", show=False),
        Binding("4", "show_mode('sun')", "Sun Digraph", show=False),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = "exec"
        self.exec_graph = None

    def compose(self) -> ComposeResult:
        yield GraphTabs(id="graph-tabs")
        # The graph gets the full width; summary, status and the event stream share the bottom row.
        with Vertical(id="topo-canvas-container"):
            with ContentSwitcher(initial="exec", id="topo-switcher"):
                c1 = DigraphCanvas(style="box", id="exec",
                                   empty_hint="No turn yet. Send a prompt in the command view; its execution graph builds here live.")
                c1.can_focus = True
                yield c1
                c2 = DigraphCanvas(style="pill", id="system", empty_hint="Collecting system topology…")
                c2.can_focus = True
                yield c2
                yield NeuralGraph3D(id="orbit")
                c4 = SunDigraphCanvas(id="sun")
                c4.can_focus = True
                yield c4
        with Horizontal(id="topo-bottom"):
            yield TurnSummaryCard(id="topo-turn")
            yield SystemStatusCard(id="topo-system")
            yield EventStreamPanel(id="topo-bus-panel")

    def on_mount(self) -> None:
        self.query_one(GraphTabs).show(self.mode)

    # ── data plumbing ───────────────────────────────────────────────────────
    def set_exec_graph(self, graph: Any) -> None:
        self.exec_graph = graph
        self.query_one("#exec", DigraphCanvas).set_graph(graph)
        try:
            self.query_one("#sun", SunDigraphCanvas).set_graph(graph)
        except Exception:
            pass
        self.query_one(TurnSummaryCard).graph = graph
        self.query_one(EventStreamPanel).graph = graph
        self.refresh_exec()

    def refresh_exec(self) -> None:
        if not self.display:
            return
        for widget in (self.query_one("#exec", DigraphCanvas), self.query_one("#sun", SunDigraphCanvas),
                       self.query_one(TurnSummaryCard), self.query_one(EventStreamPanel)):
            try:
                widget.refresh()
            except Exception:
                pass

    def set_system_graph(self, graph: Any) -> None:
        self.query_one("#system", DigraphCanvas).set_graph(graph)
        self.query_one(NeuralGraph3D).set_graph(graph)
        card = self.query_one(SystemStatusCard)
        card.facts = getattr(graph, "facts", None)
        card.refresh()

    # ── modes and animation ─────────────────────────────────────────────────
    def action_show_mode(self, mode: str) -> None:
        self.mode = mode
        self.query_one(ContentSwitcher).current = mode
        self.query_one(GraphTabs).show(mode)
        orbit = self.query_one(NeuralGraph3D)
        if mode == "orbit":
            orbit.resume_animation()
        else:
            orbit.pause_animation()
        try:
            self.query_one(f"#{mode}").focus()
        except Exception:
            pass

    def focus_canvas(self) -> None:
        try:
            self.query_one(f"#{self.mode}").focus()
        except Exception:
            pass

    def pause_animation(self) -> None:
        self.query_one(NeuralGraph3D).pause_animation()

    def resume_animation(self) -> None:
        if self.mode == "orbit":
            self.query_one(NeuralGraph3D).resume_animation()
        self.refresh_exec()
