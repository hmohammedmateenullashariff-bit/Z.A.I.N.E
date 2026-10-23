"""
tui/widgets/graph_3d.py
3D Braille/ASCII orbit renderer for the TUI.
Perspective projection with a z-buffer, Braille/ASCII edge rasterization and interactive rotation.
Draws whatever digraph it is given (the live system topology from tui/system_graph.py); node
positions are derived from the graph structure: root at the origin, its children on an inner ring,
grandchildren on an outer shell around their parent's direction.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from rich.text import Text
from textual.binding import Binding
from textual.reactive import reactive
from textual.widget import Widget

from zaine_env import running_under_tests
from tui.theme import COLOR_EMERALD, COLOR_CYAN, COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM
from tui.widgets.digraph import KIND_STYLE


class Node3D:
    """A graph node placed in 3D Euclidean space."""

    def __init__(self, node_id: str, name: str, category: str, pos3d: Tuple[float, float, float],
                 color: str, status: str = "ONLINE", depth: int = 0):
        self.node_id = node_id
        self.name = name
        self.category = category
        self.pos3d = pos3d
        self.color = color
        self.status = status
        self.depth = depth


def layout_orbit(graph: Any) -> Tuple[List[Node3D], List[Tuple[str, str]]]:
    """Places a layered digraph on concentric shells: depth 0 at the origin, depth 1 on a ring, depth 2+ on outer shells."""
    if graph is None or not getattr(graph, "nodes", None):
        return [], []
    children: Dict[str, List[str]] = {}
    has_parent = set()
    for src, dst in graph.edges:
        children.setdefault(src, []).append(dst)
        has_parent.add(dst)
    roots = [nid for nid in graph.nodes if nid not in has_parent] or [next(iter(graph.nodes))]

    pos: Dict[str, Tuple[float, float, float]] = {}
    depth_of: Dict[str, int] = {}

    def place(nid: str, depth: int, theta: float, spread: float, y: float) -> None:
        if depth == 0:
            pos[nid] = (0.0, 0.0, 0.0)
        else:
            radius = 1.35 * depth
            pos[nid] = (radius * math.cos(theta), y, radius * math.sin(theta))
        depth_of[nid] = depth
        kids = [k for k in children.get(nid, []) if k not in pos]
        if not kids:
            return
        span = (2 * math.pi) if depth == 0 else max(0.35, spread)
        # Each child's angular slice is proportional to its subtree size, so big hubs get room.
        weights = [leaves(k) for k in kids]
        total = float(sum(weights))
        cursor = theta - span / 2 if depth > 0 else 0.0
        for i, (kid, wgt) in enumerate(zip(kids, weights)):
            slice_ = span * wgt / total
            # Fan grandchildren up and down around their parent so shells don't collapse into one plane.
            ky = 0.0 if depth == 0 else y + (i - (len(kids) - 1) / 2) * (1.8 / max(2, len(kids)))
            place(kid, depth + 1, cursor + slice_ / 2, slice_, ky)
            cursor += slice_

    def leaves(nid: str, seen=None) -> int:
        seen = seen or set()
        if nid in seen:
            return 1
        seen.add(nid)
        kids = children.get(nid, [])
        return max(1, sum(leaves(k, seen) for k in kids))

    for i, root in enumerate(roots):
        place(root, 0, i * 0.7, 2 * math.pi, 0.0)

    nodes = []
    for nid, (x, y, z) in pos.items():
        n = graph.nodes[nid]
        _, color = KIND_STYLE.get(getattr(n, "kind", ""), ("NODE", COLOR_TEXT))
        nodes.append(Node3D(nid, getattr(n, "label", nid), getattr(n, "kind", ""), (x, y, z), color,
                            getattr(n, "status", "unknown").upper(), depth_of.get(nid, 0)))
    edges = [(s, d) for s, d in graph.edges if s in pos and d in pos]
    return nodes, edges


class NeuralGraph3D(Widget):
    """Interactive 3D Braille/ASCII orbit canvas."""

    DEFAULT_CSS = """
    NeuralGraph3D {
        width: 1fr;
        height: 1fr;
        background: #080d1a;
        color: #f0fdf4;
    }
    """

    can_focus = True

    BINDINGS = [
        Binding("left", "rotate_left", "Rotate Left", show=False),
        Binding("right", "rotate_right", "Rotate Right", show=False),
        Binding("up", "pitch_up", "Pitch Up", show=False),
        Binding("down", "pitch_down", "Pitch Down", show=False),
        Binding("space", "toggle_auto_rotate", "Toggle Auto Rotate", show=False),
    ]

    yaw = reactive(0.65)
    pitch = reactive(0.32)
    auto_rotate = reactive(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._timer = None
        self._camera_distance = 5.2
        self.nodes3d: List[Node3D] = []
        self.edges3d: List[Tuple[str, str]] = []

    def set_graph(self, graph: Any) -> None:
        self.nodes3d, self.edges3d = layout_orbit(graph)
        self.refresh()

    def on_mount(self) -> None:
        # The orbit starts paused; the workspace resumes it only while the orbit view is on screen.
        pass

    def on_unmount(self) -> None:
        self.pause_animation()

    def pause_animation(self) -> None:
        if self._timer:
            try:
                self._timer.pause()
            except Exception:
                pass

    def resume_animation(self) -> None:
        if running_under_tests():
            return
        if self._timer is None:
            self._timer = self.set_interval(1.0 / 15.0, self._step_frame, pause=False)
        else:
            try:
                self._timer.resume()
            except Exception:
                pass

    def _step_frame(self) -> None:
        if not self.region.width:
            return
        if self.auto_rotate:
            self.yaw = (self.yaw + 0.032) % (2.0 * math.pi)
            self.pitch = 0.30 + 0.14 * math.sin(self.yaw * 0.75)
            self.refresh()

    def action_rotate_left(self) -> None:
        self.yaw = (self.yaw - 0.18) % (2.0 * math.pi)
        self.refresh()

    def action_rotate_right(self) -> None:
        self.yaw = (self.yaw + 0.18) % (2.0 * math.pi)
        self.refresh()

    def action_pitch_up(self) -> None:
        self.pitch = max(-1.2, self.pitch - 0.12)
        self.refresh()

    def action_pitch_down(self) -> None:
        self.pitch = min(1.2, self.pitch + 0.12)
        self.refresh()

    def action_toggle_auto_rotate(self) -> None:
        self.auto_rotate = not self.auto_rotate
        self.refresh()

    def on_click(self) -> None:
        self.focus()

    def project_nodes(self, width: int, height: int) -> Dict[str, Tuple[int, int, float]]:
        """Projects node coordinates to terminal cells: node_id -> (screen_x, screen_y, depth_z)."""
        w, h = max(20, width), max(10, height)
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        cx, cy_scr = w // 2, h // 2
        extent = max((max(abs(c) for c in n.pos3d) for n in self.nodes3d), default=1.0) or 1.0
        # Terminal cells are ~2:1, so the vertical scale is roughly half the horizontal one.
        scale_x = max(8.0, (w * 0.42) / extent)
        scale_y = max(4.0, min(scale_x * 0.46, (h * 0.42) / extent))
        D = self._camera_distance
        projected: Dict[str, Tuple[int, int, float]] = {}
        for node in self.nodes3d:
            x, y, z = node.pos3d
            y1 = y * cp - z * sp
            z1 = y * sp + z * cp
            x2 = x * cy + z1 * sy
            z2 = -x * sy + z1 * cy
            k = D / max(0.5, D + z2)
            projected[node.node_id] = (int(round(cx + x2 * k * scale_x)), int(round(cy_scr - y1 * k * scale_y)), z2)
        return projected

    def render(self) -> Text:
        w = self.size.width or 80
        h = self.size.height or 24
        plot_h = max(6, h - 2)
        plot_w = max(20, w)
        t = Text()
        t.append(" 3D SYSTEM ORBIT ", style=f"bold {COLOR_CYAN}")
        t.append(f"· {len(self.nodes3d)} nodes · {len(self.edges3d)} edges · ", style=COLOR_TEXT_MUTED)
        t.append("AUTO-ORBIT\n" if self.auto_rotate else "HOLD\n", style=f"bold {COLOR_EMERALD}" if self.auto_rotate else "bold #f59e0b")
        if not self.nodes3d:
            t.append("\n" * (plot_h // 2) + "System topology not collected yet.".center(plot_w), style=f"italic {COLOR_TEXT_MUTED}")
            return t

        projected = self.project_nodes(plot_w, plot_h)
        grid_char = [[" "] * plot_w for _ in range(plot_h)]
        grid_style = [[""] * plot_w for _ in range(plot_h)]
        grid_z = [[-999.0] * plot_w for _ in range(plot_h)]

        for u_id, v_id in self.edges3d:
            x0, y0, z0 = projected[u_id]
            x1, y1, z1 = projected[v_id]
            dx, dy = x1 - x0, y1 - y0
            steps = max(abs(dx), abs(dy) * 2, 1)
            for s in range(1, steps):
                f = s / steps
                px, py = int(round(x0 + dx * f)), int(round(y0 + dy * f))
                pz = z0 + (z1 - z0) * f
                if 0 <= px < plot_w and 0 <= py < plot_h and pz > grid_z[py][px]:
                    if pz < -0.8:
                        ch, st = "⠶", "#00d2ff"
                    elif pz < 0.2:
                        ch, st = "·", "#3b82f6"
                    elif pz < 0.8:
                        ch, st = "·", "#1e3a5f"
                    else:
                        ch, st = ".", "#1e293b"
                    grid_char[py][px], grid_style[py][px], grid_z[py][px] = ch, st, pz

        # Nearer nodes (more negative z after rotation) are drawn last so they sit on top.
        for node in sorted(self.nodes3d, key=lambda n: -projected[n.node_id][2]):
            sx, sy_, z = projected[node.node_id]
            if not (0 <= sx < plot_w and 0 <= sy_ < plot_h):
                continue
            near = z < 0.0
            symbol = "⣿" if z < -0.8 else ("⣶" if near else ("⠶" if z < 0.8 else "⠄"))
            style = f"bold {node.color}" if near else (node.color if z < 0.8 else f"dim {node.color}")
            grid_char[sy_][sx], grid_style[sy_][sx], grid_z[sy_][sx] = symbol, style, 999.0
            if not near and node.depth > 1:
                continue  # far-side leaves stay unlabeled so front labels stay readable
            label = f" {node.name}"
            lx = sx + 1 if sx + 1 + len(label) < plot_w else max(0, sx - len(label))
            lstyle = f"bold {node.color}" if near else "dim #64748b"
            for i, ch in enumerate(label):
                col = lx + i
                if 0 <= col < plot_w and grid_z[sy_][col] < 900.0:
                    grid_char[sy_][col], grid_style[sy_][col], grid_z[sy_][col] = ch, lstyle, 400.0

        for y in range(plot_h):
            run, cur = "", None
            for x in range(plot_w):
                st = grid_style[y][x]
                if st != cur and run:
                    t.append(run, style=cur or COLOR_TEXT)
                    run = ""
                cur = st
                run += grid_char[y][x]
            if run:
                t.append(run, style=cur or COLOR_TEXT)
            t.append("\n")
        t.append(" [←/→/↑/↓] Rotate · [Space] Hold/Orbit", style=COLOR_TEXT_DIM)
        return t
