"""
tui/widgets/digraph.py
Layered left-to-right directed-graph renderer for the TUI.

Draws any graph exposing `.nodes` (id -> node with kind/label/detail/status), `.edges` [(src, dst)]
and `.layers()` (columns of node ids). Used for the live execution DAG ("box" style) and the
system topology ("pill" style). Also renders a compact vertical trace for the HUD.
"""

from typing import Any, Dict, List, Optional, Tuple

from rich.text import Text
from textual.widget import Widget
from textual.containers import VerticalScroll
from textual.widgets import Static
from textual.binding import Binding
from textual.app import ComposeResult

from tui.theme import (
    COLOR_EMERALD, COLOR_CYAN, COLOR_VIOLET_BRIGHT, COLOR_AMBER, COLOR_ROSE,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM, COLOR_BORDER,
)

KIND_STYLE = {
    "prompt": ("USER", COLOR_EMERALD),
    "router": ("ROUTER", COLOR_VIOLET_BRIGHT),
    "agent": ("AGENT", COLOR_VIOLET_BRIGHT),
    "model": ("LLM", COLOR_CYAN),
    "tool": ("TOOL", COLOR_AMBER),
    "approval": ("GUARD", COLOR_AMBER),
    "reply": ("REPLY", COLOR_EMERALD),
    "error": ("HALT", COLOR_ROSE),
    # system topology kinds
    "client": ("CLIENT", COLOR_EMERALD),
    "service": ("CORE", COLOR_CYAN),
    "group": ("HUB", COLOR_VIOLET_BRIGHT),
    "llm": ("MODEL", COLOR_CYAN),
    "cluster": ("CLUSTER", COLOR_AMBER),
    "store": ("STORE", COLOR_VIOLET_BRIGHT),
    "channel": ("LINK", COLOR_EMERALD),
}

STATUS_STYLE = {
    "running": ("◆", COLOR_CYAN, "RUNNING"),
    "ok": ("●", COLOR_EMERALD, "OK"),
    "failed": ("✗", COLOR_ROSE, "FAILED"),
    "waiting": ("◌", COLOR_AMBER, "WAITING"),
    "blocked": ("⊘", COLOR_ROSE, "BLOCKED"),
    "cancelled": ("■", COLOR_AMBER, "CANCELLED"),
    "online": ("●", COLOR_EMERALD, "ONLINE"),
    "loaded": ("●", COLOR_CYAN, "IN VRAM"),
    "idle": ("○", COLOR_TEXT_MUTED, "IDLE"),
    "offline": ("○", COLOR_ROSE, "OFFLINE"),
    "unknown": ("·", COLOR_TEXT_DIM, "N/A"),
}

SPINNER = "◐◓◑◒"
GAP = 4        # columns between boxes (room for routed edges)
MARGIN = 4     # left margin for the "earlier columns" marker
PILL_MAX = 30  # widest pill column, so a whole system tree fits next to the sidebar


def _status(node: Any, frame: int) -> Tuple[str, str, str]:
    glyph, color, word = STATUS_STYLE.get(getattr(node, "status", "unknown"), STATUS_STYLE["unknown"])
    if getattr(node, "status", "") == "running":
        glyph = SPINNER[frame % len(SPINNER)]
    return glyph, color, word


def _fit(text: str, width: int) -> str:
    text = str(text or "")
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


class _Grid:
    """Character canvas with per-cell styles; later writes win unless the cell is locked."""

    def __init__(self, width: int, height: int) -> None:
        self.w, self.h = width, height
        self.ch = [[" "] * width for _ in range(height)]
        self.st = [[""] * width for _ in range(height)]
        self.lock = [[False] * width for _ in range(height)]

    def put(self, x: int, y: int, ch: str, style: str, lock: bool = False, force: bool = False) -> None:
        if 0 <= x < self.w and 0 <= y < self.h and (force or not self.lock[y][x]):
            self.ch[y][x] = ch
            self.st[y][x] = style
            if lock:
                self.lock[y][x] = True

    # (new segment, existing cell) -> merged junction glyph
    _MERGE = {
        ("│", "─"): "┼", ("─", "│"): "┼", ("│", "┬"): "┼", ("│", "┴"): "┼",
        ("╮", "─"): "┬", ("╭", "─"): "┬", ("╯", "─"): "┴", ("╰", "─"): "┴",
        ("╮", "│"): "┤", ("╯", "│"): "┤", ("╭", "│"): "├", ("╰", "│"): "├",
        ("╮", "╭"): "┬", ("╭", "╮"): "┬", ("╯", "╰"): "┴", ("╰", "╯"): "┴",
        ("╮", "╯"): "┤", ("╯", "╮"): "┤", ("╭", "╰"): "├", ("╰", "╭"): "├",
        ("─", "┤"): "┼", ("─", "├"): "┼", ("│", "┬"): "┼", ("│", "┴"): "┼",
        ("╮", "┴"): "┼", ("╯", "┬"): "┼", ("╰", "┬"): "┼", ("╭", "┴"): "┼",
    }

    def line(self, x: int, y: int, ch: str, style: str) -> None:
        """Edge segment or corner; meeting another edge's glyph merges into a tee or crossing."""
        if not (0 <= x < self.w and 0 <= y < self.h) or self.lock[y][x]:
            return
        cur = self.ch[y][x]
        merged = self._MERGE.get((ch, cur))
        if merged is None and cur in ("┼", "┬", "┴", "├", "┤"):
            return  # keep an existing junction rather than flatten it
        self.ch[y][x] = merged or ch
        self.st[y][x] = style

    def text(self, x: int, y: int, s: str, style: str, lock: bool = True) -> None:
        for i, c in enumerate(s):
            self.put(x + i, y, c, style, lock=lock, force=lock)

    def to_text(self) -> Text:
        out = Text()
        for y in range(self.h):
            run, cur = "", None
            for x in range(self.w):
                st = self.st[y][x]
                if st != cur and run:
                    out.append(run, style=cur or COLOR_TEXT)
                    run = ""
                cur = st
                run += self.ch[y][x]
            if run:
                out.append(run, style=cur or COLOR_TEXT)
            if y < self.h - 1:
                out.append("\n")
        return out


def render_digraph(graph: Any, width: int, height: int, style: str = "box", frame: int = 0,
                   empty_hint: str = "No data yet.") -> Text:
    """Renders the graph into a Text block of exactly `height` lines (or fewer when empty)."""
    width, height = max(30, width), max(6, height)
    if graph is None or not getattr(graph, "nodes", None):
        t = Text()
        t.append("\n" * max(0, height // 2 - 1))
        t.append(_fit(empty_hint, width).center(width), style=f"italic {COLOR_TEXT_MUTED}")
        return t

    layers: List[List[str]] = [list(col) for col in graph.layers()]
    # Barycenter ordering: place each node near the average row of its parents to avoid crossings.
    preds: Dict[str, List[str]] = {}
    for src, dst in graph.edges:
        preds.setdefault(dst, []).append(src)
    row_of: Dict[str, int] = {nid: i for i, nid in enumerate(layers[0])} if layers else {}
    for col in layers[1:]:
        def bary(nid: str, _col=col) -> float:
            rows = [row_of[p] for p in preds.get(nid, []) if p in row_of]
            return sum(rows) / len(rows) if rows else float(_col.index(nid))
        col.sort(key=bary)
        row_of.update({nid: i for i, nid in enumerate(col)})
    box_h = 4 if style == "box" else 1
    row_gap = 1 if style == "box" else 0
    ncols = len(layers)
    usable = width - MARGIN
    nodes = graph.nodes
    def fit(gap: int):
        if style == "box":
            uniform = max(15, min(28, (usable - gap * (ncols - 1)) // max(1, ncols)))
            widths = [uniform] * ncols
        else:
            # Pills size each column to its longest "glyph label  detail" line.
            widths = [
                max(14, min(PILL_MAX, max(len(f"{getattr(nodes[n], 'label', n)}  {getattr(nodes[n], 'detail', '')}") + 3 for n in col)))
                for col in layers
            ]
        # Hide leading columns until the rest fits.
        h = 0
        while h < ncols - 1 and sum(widths[h:]) + gap * (ncols - h - 1) > usable:
            h += 1
        return widths, h

    # A 5-column gap leaves two vertical lanes, so edges from different sources never share one;
    # fall back to 4 only when that keeps more columns on screen.
    gap = GAP + 1
    col_w, hidden = fit(gap)
    if hidden:
        narrow_w, narrow_hidden = fit(GAP)
        if narrow_hidden < hidden:
            gap, col_w, hidden = GAP, narrow_w, narrow_hidden
    visible_layers = layers[hidden:]
    vis_w = col_w[hidden:]
    width_of: Dict[str, int] = {nid: vis_w[ci] for ci, col in enumerate(visible_layers) for nid in col}

    max_rows = max(len(col) for col in visible_layers)
    rows_fit = max(1, (height + row_gap) // (box_h + row_gap))

    pos: Dict[str, Tuple[int, int]] = {}
    col_of: Dict[str, int] = {}
    clipped = 0
    x = MARGIN
    for ci, col in enumerate(visible_layers):
        shown = col[:rows_fit]
        clipped += len(col) - len(shown)
        offset = ((min(max_rows, rows_fit) - len(shown)) * (box_h + row_gap)) // 2
        for ri, nid in enumerate(shown):
            pos[nid] = (x, offset + ri * (box_h + row_gap))
            col_of[nid] = ci
        x += vis_w[ci] + gap
    # Edges that skip columns run along lanes below every box, so they never pass behind another node.
    lane_y = (max((y for _, y in pos.values()), default=0) + box_h + (1 if style == "box" else 0))
    next_lane = 0

    grid = _Grid(width, height)

    # 1. Edges first (boxes are drawn on top and lock their cells). Collected, then drawn in passes:
    #    horizontals, verticals, corners, arrows, so junctions merge instead of overwriting each other.
    horiz: List[Tuple[int, int, int, str]] = []
    vert: List[Tuple[int, int, int, str]] = []
    corners: List[Tuple[int, int, str, str]] = []
    arrows: List[Tuple[int, int, str]] = []
    # Vertical lanes are per source node: a parent's children share one trunk (clean fan-out),
    # while different parents turning in the same gap get separate lanes (no overlapping routes).
    lane_of_src: Dict[str, int] = {}
    lanes_in_gap: Dict[int, int] = {}
    for src, dst in graph.edges:
        if src not in pos or dst not in pos:
            continue
        sx, sy = pos[src]
        dx, dy = pos[dst]
        y0 = sy + (1 if style == "box" else 0)
        y1 = dy + (1 if style == "box" else 0)
        x0 = sx + width_of[src]
        x1 = dx - 1
        if x1 <= x0:
            continue
        # One vertical lane per source node in each gap (shared by its short and long edges).
        if src not in lane_of_src:
            lane_of_src[src] = lanes_in_gap.get(x0, 0)
            lanes_in_gap[x0] = lane_of_src[src] + 1
        src_lane = lane_of_src[src] % max(1, gap - 3)
        span = col_of[dst] - col_of[src]
        if span > 1 and lane_y + next_lane < height:
            ly = lane_y + next_lane
            next_lane += 1
            down_x, up_x = x0 + 1 + src_lane, x1 - 1
            dst_status = getattr(nodes[dst], "status", "")
            est = (f"bold {COLOR_CYAN}" if dst_status in ("running", "waiting") else
                   COLOR_ROSE if dst_status in ("failed", "blocked") else
                   (COLOR_EMERALD if style == "box" else COLOR_TEXT_DIM) if dst_status in ("ok", "online", "loaded")
                   else COLOR_TEXT_DIM)
            horiz.append((y0, x0, down_x, est))
            vert.append((down_x, y0 + 1, ly, est))
            corners.append((down_x, y0, "╮", est))
            corners.append((down_x, ly, "╰", est))
            horiz.append((ly, down_x + 1, up_x, est))
            corners.append((up_x, ly, "╯", est))
            vert.append((up_x, y1 + 1, ly, est))
            corners.append((up_x, y1, "╭", est))
            horiz.append((y1, up_x + 1, x1, est))
            arrows.append((x1, y1, est))
            continue
        mx = min(x1 - 1, x0 + 1 + (0 if y0 == y1 else src_lane))
        dst_status = getattr(nodes[dst], "status", "")
        if dst_status in ("running", "waiting"):
            est = f"bold {COLOR_CYAN}"
        elif dst_status in ("failed", "blocked"):
            est = COLOR_ROSE
        elif dst_status in ("ok", "online", "loaded"):
            est = COLOR_EMERALD if style == "box" else COLOR_TEXT_DIM
        else:
            est = COLOR_TEXT_DIM
        if y1 == y0:
            horiz.append((y0, x0, x1, est))
        else:
            down = y1 > y0
            horiz.append((y0, x0, mx, est))
            horiz.append((y1, mx + 1, x1, est))
            vert.append((mx, min(y0, y1) + 1, max(y0, y1), est))
            corners.append((mx, y0, "╮" if down else "╯", est))
            corners.append((mx, y1, "╰" if down else "╭", est))
        arrows.append((x1, y1, est))

    for y, xa, xb, est in horiz:
        for x in range(xa, xb):
            grid.line(x, y, "─", est)
    for x, ya, yb, est in vert:
        for y in range(ya, yb):
            grid.line(x, y, "│", est)
    for x, y, ch, est in corners:
        grid.line(x, y, ch, est)
    for x, y, est in arrows:
        grid.put(x, y, "▶", est)

    # 2. Nodes.
    for nid, (x, y) in pos.items():
        node = nodes[nid]
        box_w = width_of[nid]
        tag, kcolor = KIND_STYLE.get(getattr(node, "kind", ""), ("NODE", COLOR_TEXT))
        glyph, scolor, word = _status(node, frame)
        label = getattr(node, "label", nid)
        detail = getattr(node, "detail", "")
        if style == "pill":
            body = _fit(f"{label}  {detail}".rstrip(), box_w - 3)
            grid.text(x, y, f"{glyph} ", f"bold {scolor}")
            grid.text(x + 2, y, body.ljust(box_w - 2), f"bold {kcolor}" if getattr(node, "kind", "") in ("client", "service", "group") else COLOR_TEXT)
            continue
        border = f"bold {kcolor}" if getattr(node, "status", "") in ("running", "waiting") else kcolor
        inner = box_w - 2
        head = f"─ {tag} "
        stat = f" {glyph} {word} "
        fill = max(0, inner - len(head) - len(stat))
        grid.text(x, y, "╭", border)
        grid.text(x + 1, y, head, f"bold {kcolor}")
        grid.text(x + 1 + len(head), y, "─" * fill, border)
        grid.text(x + 1 + len(head) + fill, y, _fit(stat, inner - len(head)), f"bold {scolor}")
        grid.text(x + box_w - 1, y, "╮", border)
        meta = getattr(node, "meta", {}) or {}
        line2 = detail
        dur = getattr(node, "duration_s", None)
        if getattr(node, "kind", "") == "model" and meta.get("eval_count"):
            line2 = f"{meta['eval_count']} tok · {meta.get('tok_s', 0):.1f} tok/s"
        elif dur is not None and getattr(node, "kind", "") in ("tool", "approval") and dur >= 0.05:
            line2 = f"{_fit(detail, inner - 9)} {dur:.1f}s"
        if getattr(node, "kind", "") == "approval" and meta.get("outcome"):
            line2 = f"{meta.get('proposal_id', '')} {meta['outcome']}"
        grid.text(x, y + 1, "│", border)
        grid.text(x + 1, y + 1, (" " + _fit(label, inner - 1)).ljust(inner), f"bold {COLOR_TEXT}")
        grid.text(x + box_w - 1, y + 1, "│", border)
        grid.text(x, y + 2, "│", border)
        grid.text(x + 1, y + 2, (" " + _fit(line2, inner - 1)).ljust(inner), COLOR_TEXT_MUTED)
        grid.text(x + box_w - 1, y + 2, "│", border)
        grid.text(x, y + 3, "╰" + "─" * inner + "╯", border)

    if hidden:
        grid.text(0, 1 if style == "box" else 0, f"◀+{hidden}", f"bold {COLOR_AMBER}")
    if clipped:
        grid.text(max(0, width - 12), height - 1, f"▼ +{clipped} more", f"bold {COLOR_AMBER}")
    return grid.to_text()


def render_trace(graph: Any, width: int, max_lines: int = 8, frame: int = 0) -> Text:
    """Compact vertical execution trace (topological order) for narrow panels like the HUD."""
    t = Text()
    if graph is None or not getattr(graph, "nodes", None):
        t.append("  n/a (no turn yet)\n", style=COLOR_TEXT_DIM)
        return t
    order = [nid for col in graph.layers() for nid in col]
    if len(order) > max_lines:
        t.append(f"  ⋮ {len(order) - max_lines + 1} earlier steps\n", style=COLOR_TEXT_DIM)
        order = order[-(max_lines - 1):]
    for i, nid in enumerate(order):
        node = graph.nodes[nid]
        tag, kcolor = KIND_STYLE.get(node.kind, ("NODE", COLOR_TEXT))
        glyph, scolor, _ = _status(node, frame)
        connector = "└▶" if i == len(order) - 1 else "├▶"
        t.append(f"  {connector}", style=COLOR_BORDER)
        t.append(f"{glyph} ", style=f"bold {scolor}")
        t.append(f"{tag:<6} ", style=f"bold {kcolor}")
        rest = node.label if node.kind != "tool" else node.label
        t.append(_fit(rest, max(4, width - 14)) + "\n", style=COLOR_TEXT)
    return t


class DigraphCanvas(Widget):
    """Textual widget that renders a digraph and animates running nodes."""

    DEFAULT_CSS = """
    DigraphCanvas {
        width: 1fr;
        height: 1fr;
        background: #080d1a;
    }
    """

    def __init__(self, style: str = "box", empty_hint: str = "No data yet.", **kwargs):
        super().__init__(**kwargs)
        self.graph_style = style
        self.empty_hint = empty_hint
        self.graph: Optional[Any] = None
        self.frame = 0
        self._timer = None

    def set_graph(self, graph: Any) -> None:
        self.graph = graph
        self.refresh()

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.25, self._tick)

    def _tick(self) -> None:
        # Only animate while something is actually running and the canvas is on screen.
        if self.graph is not None and getattr(self.graph, "is_active", False) and self.region.width:
            self.frame += 1
            self.refresh()

    def render(self) -> Text:
        return render_digraph(self.graph, self.size.width, self.size.height, self.graph_style,
                              self.frame, self.empty_hint)


class SunDigraphCanvas(VerticalScroll):
    """
    Solar / Sun Digraph workspace widget (Tab [4]).
    Renders an animated radiant solar directed-graph that activates and evolves
    live as the model answers queries, showing the solar core, cognitive rays,
    active agent node, streaming answer flow, and live inference metrics.
    Fully scrollable vertically and horizontally with mouse wheel and keyboard.
    """

    DEFAULT_CSS = """
    SunDigraphCanvas {
        width: 1fr;
        height: 1fr;
        background: #060913;
        overflow-y: scroll;
        overflow-x: auto;
    }
    #sun-body {
        width: auto;
        height: auto;
    }
    """

    CORONA_GLYPHS = ["☼", "✦", "✧", "✴", "✺", "✹", "·", "∘", "◦"]

    BINDINGS = [
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("home", "scroll_home", "Top", show=False),
        Binding("end", "scroll_end", "Bottom", show=False),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.can_focus = True
        self.graph: Optional[Any] = None
        self.frame = 0
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Static(id="sun-body")

    def set_graph(self, graph: Any) -> None:
        self.graph = graph
        self._update_display()

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.2, self._tick)
        self._update_display()

    def _tick(self) -> None:
        self.frame += 1
        self._update_display()

    def _update_display(self) -> None:
        try:
            body = self.query_one("#sun-body", Static)
            body.update(self.build_sun_text())
        except Exception:
            pass

    def on_mouse_scroll_up(self, event: Any) -> None:
        self.scroll_up(animate=False)

    def on_mouse_scroll_down(self, event: Any) -> None:
        self.scroll_down(animate=False)

    def render(self) -> Text:
        return self.build_sun_text()

    def build_sun_text(self) -> Text:
        w = max(40, self.size.width or 100)
        t = Text()

        g = self.graph
        is_active = g is not None and getattr(g, "is_active", False)
        summary = g.summary() if g is not None else {}
        prompt = summary.get("prompt", "")
        agent = summary.get("agent", "J.A.R.V.I.S.")
        model = summary.get("model", "zaine-fast-3b")
        tok_s = summary.get("tok_s", 0.0)
        tokens = summary.get("tokens", 0)
        tools = summary.get("tools", 0)
        hops = summary.get("hops", 1)

        # 1. Header Banner
        t.append(" ☼ SUN COGNITIVE DIGRAPH ", style=f"bold {COLOR_AMBER}")
        t.append("· Real-time Solar Answering DAG\n", style=COLOR_TEXT_DIM)
        t.append("─" * min(w - 2, 70) + "\n\n", style=COLOR_BORDER)

        if g is None or g.is_empty:
            t.append("  [☼ SUN CORE IDLE]\n", style=f"bold {COLOR_AMBER}")
            t.append("  Waiting for user prompt in command view. Once answered, the solar digraph pulses here.\n", style=f"italic {COLOR_TEXT_MUTED}")
            t.append("  Switch back with [F3] or select [1] Execution DAG, [2] System, [3] Orbit 3D.\n", style=COLOR_TEXT_DIM)
            return t

        corona = self.CORONA_GLYPHS[self.frame % len(self.CORONA_GLYPHS)]
        pulse_color = COLOR_AMBER if is_active else COLOR_EMERALD

        # Digraph Layer 1: Prompt Input Node (46 cols aligned)
        p_short = (prompt[:35] + "…") if len(prompt) > 36 else prompt
        t.append("  ╭── [1. USER PROMPT] ──────────────────────╮\n", style=COLOR_EMERALD)
        t.append(f"  │ ❝ {p_short:<36} ❞ │\n", style=f"bold {COLOR_TEXT}")
        t.append("  ╰────────────────────┬─────────────────────╯\n", style=COLOR_EMERALD)
        t.append("                       │\n", style=COLOR_BORDER)
        t.append("                       ▼\n", style=f"bold {COLOR_EMERALD}")

        # Digraph Layer 2: Solar Agent Core (The Sun Hub) (46 cols aligned)
        status_label = "ACTIVE" if is_active else "READY "
        agent_s = (agent[:17] + "…") if len(agent) > 18 else agent
        model_s = (model[:16] + "…") if len(model) > 17 else model
        t.append(f"  ╭── [2. SOLAR CORE: {status_label}] ───────────────╮\n", style=pulse_color)
        t.append(f"  │   {corona} ACTIVE AGENT: @{agent_s:<18} {corona}  │\n", style=f"bold {COLOR_CYAN}")
        t.append(f"  │   ☼ COGNITIVE MODEL: {model_s:<17} ☼ │\n", style=f"bold {COLOR_VIOLET_BRIGHT}")
        t.append("  ╰────────────────────┬─────────────────────╯\n", style=pulse_color)
        t.append("                       │\n", style=COLOR_BORDER)
        t.append("                       ▼\n", style=f"bold {pulse_color}")

        # Digraph Layer 3: Cognitive Deliberation / Tools (46 cols aligned)
        hops_s = str(hops)[:2]
        tools_s = str(tools)[:4]
        t.append("  ╭── [3. COGNITIVE PIPELINE] ───────────────╮\n", style=COLOR_VIOLET_BRIGHT)
        t.append(f"  │   Hops: {hops_s:<2}  │ Tool Runs: {tools_s:<4}            │\n", style=COLOR_TEXT)
        t.append(f"  │   Rate: {tok_s:>5.1f} tok/s ({tokens:<4} tok)           │\n", style=f"bold {COLOR_CYAN}")
        t.append("  ╰────────────────────┬─────────────────────╯\n", style=COLOR_VIOLET_BRIGHT)
        t.append("                       │\n", style=COLOR_BORDER)
        t.append("                       ▼\n", style=f"bold {COLOR_VIOLET_BRIGHT}")

        # Digraph Layer 4: Model Output Node (Live Answering) (46 cols aligned)
        t.append("  ╭── [4. MODEL STREAMING OUTPUT] ───────────╮\n", style=COLOR_EMERALD if not is_active else COLOR_CYAN)
        ans_state = "✦ STREAMING LIVE TO USER..." if is_active else "● SYNTHESIZED & DISPATCHED"
        t.append(f"  │   {ans_state:<38} │\n", style=f"bold {COLOR_EMERALD if not is_active else COLOR_CYAN}")
        t.append("  ╰──────────────────────────────────────────╯\n\n", style=COLOR_EMERALD if not is_active else COLOR_CYAN)

        t.append(f"  [☼ Status: {'ACTIVE' if is_active else 'READY'}] · Turn #{summary.get('turn', 1)} · [1] DAG · [2] System · [3] Orbit · [4] Sun · [F3] Back\n", style=COLOR_TEXT_DIM)
        return t
