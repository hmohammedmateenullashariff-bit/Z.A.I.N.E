"""
tui/widgets/graph_3d.py
3D Braille and High-Density ASCII Neural Node Graph Engine for Z.A.I.N.E TUI.
Renders a real-time rotating 3D neural topology graph with depth-buffered
perspective projection, Braille/ASCII edge rasterization, and interactive controls.
"""

import sys
import math
import time
from typing import Dict, Tuple, List, Optional
from textual.widget import Widget
from textual.reactive import reactive
from textual.binding import Binding
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


class Node3D:
    """Represents a neural node in 3D Euclidean space."""

    def __init__(
        self,
        node_id: str,
        name: str,
        category: str,
        pos3d: Tuple[float, float, float],
        color: str,
        status: str = "ONLINE",
    ):
        self.node_id = node_id
        self.name = name
        self.category = category  # "core", "model", "memory", "tool"
        self.pos3d = pos3d  # (x, y, z)
        self.color = color
        self.status = status


# Pre-defined Neural Node Graph Topology
TOPOLOGY_NODES: List[Node3D] = [
    # Core Engine Nodes
    Node3D("core", "Z.A.I.N.E Core", "core", (0.0, 0.0, 0.0), COLOR_EMERALD, "MASTER"),
    Node3D("reflex", "Reflex-7B", "model", (-1.8, 1.1, 0.6), COLOR_CYAN, "TIER_0"),
    Node3D("coder", "Coder-7B", "model", (1.8, 1.1, -0.6), COLOR_CYAN, "TIER_1"),
    # Memory Nodes (Obsidian Vault Categories)
    Node3D("sys_mem", "00_System", "memory", (-1.4, -1.3, 1.2), COLOR_VIOLET, "VAULT"),
    Node3D("episodic_mem", "10_Episodic", "memory", (0.0, -1.9, 1.3), COLOR_VIOLET, "VAULT"),
    Node3D("knowledge_mem", "20_Knowledge", "memory", (1.4, -1.3, 1.2), COLOR_VIOLET, "VAULT"),
    # Tool Cluster Nodes
    Node3D("filesystem", "FileSystem", "tool", (-2.2, 0.1, -1.5), COLOR_AMBER, "ACTIVE"),
    Node3D("shell", "Shell", "tool", (-0.9, 1.8, -1.2), COLOR_AMBER, "GUARDED"),
    Node3D("websearch", "WebSearch", "tool", (0.9, 1.8, -1.2), COLOR_AMBER, "READY"),
    Node3D("vision", "Vision", "tool", (2.2, 0.1, -1.5), COLOR_AMBER, "MOONDREAM"),
]

TOPOLOGY_EDGES: List[Tuple[str, str]] = [
    # Core to Models
    ("core", "reflex"),
    ("core", "coder"),
    # Core to Memory Vault
    ("core", "sys_mem"),
    ("core", "episodic_mem"),
    ("core", "knowledge_mem"),
    # Core to Tool Clusters
    ("core", "filesystem"),
    ("core", "shell"),
    ("core", "websearch"),
    ("core", "vision"),
    # Inter-Node Synapses
    ("reflex", "shell"),
    ("reflex", "websearch"),
    ("reflex", "episodic_mem"),
    ("coder", "filesystem"),
    ("coder", "shell"),
    ("coder", "knowledge_mem"),
    ("sys_mem", "episodic_mem"),
    ("episodic_mem", "knowledge_mem"),
    ("filesystem", "vision"),
]


class NeuralGraph3D(Widget):
    """Interactive 3D Braille/ASCII Neural Topology Canvas Widget."""

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
    roll = reactive(0.0)
    auto_rotate = reactive(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._timer = None
        self._fps_timestamp = time.time()
        self._camera_distance = 4.4

    def on_mount(self) -> None:
        """Start ~15 FPS rotation timer on widget mount."""
        if not ("unittest" in sys.modules or "pytest" in sys.modules):
            self.resume_animation()

    def on_unmount(self) -> None:
        """Clean shutdown of animation timer."""
        self.pause_animation()

    def pause_animation(self) -> None:
        """Pauses frame updates to consume 0% CPU when in background."""
        if self._timer:
            try:
                self._timer.pause()
            except Exception:
                pass

    def resume_animation(self) -> None:
        """Resumes ~15 FPS frame updates when active."""
        if "unittest" in sys.modules or "pytest" in sys.modules:
            return
        if self._timer is None:
            self._timer = self.set_interval(1.0 / 15.0, self._step_frame, pause=False)
        else:
            try:
                self._timer.resume()
            except Exception:
                pass

    def _step_frame(self) -> None:
        """Updates rotation angles and triggers refresh."""
        if not self.visible or not self.display:
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
        """
        Projects 3D node coordinates to 2D terminal coordinates with perspective scaling.
        Returns mapping: node_id -> (screen_x, screen_y, depth_z).
        """
        w = max(20, width)
        h = max(10, height)

        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        cr, sr = math.cos(self.roll), math.sin(self.roll)

        cx = w // 2
        cy_scr = h // 2

        # Scale accounts for terminal 2:1 character cell aspect ratio
        scale_x = max(12.0, w * 0.20)
        scale_y = max(6.0, scale_x * 0.44)

        D = self._camera_distance
        projected: Dict[str, Tuple[int, int, float]] = {}

        for node in TOPOLOGY_NODES:
            x, y, z = node.pos3d

            # Pitch (Rotation around X)
            y1 = y * cp - z * sp
            z1 = y * sp + z * cp
            x1 = x

            # Yaw (Rotation around Y)
            x2 = x1 * cy + z1 * sy
            z2 = -x1 * sy + z1 * cy
            y2 = y1

            # Roll (Rotation around Z)
            x3 = x2 * cr - y2 * sr
            y3 = x2 * sr + y2 * cr
            z3 = z2

            # Perspective projection factor
            k = D / max(0.5, D + z3)

            sx = int(round(cx + x3 * k * scale_x))
            sy_coord = int(round(cy_scr - y3 * k * scale_y))

            projected[node.node_id] = (sx, sy_coord, z3)

        return projected

    def render(self) -> Text:
        """Renders the depth-buffered 3D neural graph into a Rich Text renderable."""
        w = self.size.width or 80
        h = self.size.height or 24

        # Reserve top 3 rows for title and stats, bottom 2 rows for controls
        header_height = 3
        footer_height = 2
        plot_h = max(6, h - header_height - footer_height)
        plot_w = max(20, w)

        # 1. Project nodes to 2D space
        projected = self.project_nodes(plot_w, plot_h)

        # 2. Initialize 2D character, style, and Z-buffer grids
        grid_char = [[" "] * plot_w for _ in range(plot_h)]
        grid_style = [[""] * plot_w for _ in range(plot_h)]
        grid_z = [[-999.0] * plot_w for _ in range(plot_h)]

        # 3. Draw 3D Edges with depth interpolation
        for u_id, v_id in TOPOLOGY_EDGES:
            if u_id not in projected or v_id not in projected:
                continue

            x0, y0, z0 = projected[u_id]
            x1, y1, z1 = projected[v_id]

            dx = x1 - x0
            dy = y1 - y0
            steps = max(abs(dx), abs(dy) * 2, 1)

            for s in range(1, steps):
                t = s / steps
                px = int(round(x0 + dx * t))
                py = int(round(y0 + dy * t))
                pz = z0 + (z1 - z0) * t

                if 0 <= px < plot_w and 0 <= py < plot_h:
                    if pz > grid_z[py][px]:
                        if pz > 0.6:
                            ch = "⠶"
                            st = "#00d2ff"
                        elif pz > -0.2:
                            ch = "·"
                            st = "#3b82f6"
                        elif pz > -0.8:
                            ch = "·"
                            st = "#1e293b"
                        else:
                            ch = "."
                            st = "#0f172a"

                        grid_char[py][px] = ch
                        grid_style[py][px] = st
                        grid_z[py][px] = pz

        # 4. Draw Nodes with depth-shaded Braille/Block symbols
        # Sort nodes from back to front for clean rendering
        sorted_nodes = sorted(TOPOLOGY_NODES, key=lambda n: projected[n.node_id][2])

        for node in sorted_nodes:
            sx, sy_coord, z_depth = projected[node.node_id]

            if 0 <= sx < plot_w and 0 <= sy_coord < plot_h:
                # Select depth symbol: ⣿ (high-density foreground) down to ⠄ (dim background)
                if z_depth > 0.6:
                    symbol = "⣿"
                    style = f"bold {node.color}"
                elif z_depth > 0.0:
                    symbol = "⣶"
                    style = f"bold {node.color}"
                elif z_depth > -0.8:
                    symbol = "⠶"
                    style = f"{node.color}"
                else:
                    symbol = "⠄"
                    style = f"dim {node.color}"

                grid_char[sy_coord][sx] = symbol
                grid_style[sy_coord][sx] = style
                grid_z[sy_coord][sx] = 999.0  # Lock cell so edges/labels don't overwrite

                # Node Label
                label = f" {node.name}"
                lx = sx + 1
                if lx + len(label) >= plot_w:
                    lx = max(0, sx - len(label))

                label_style = f"bold {node.color}" if z_depth > -0.2 else "dim #64748b"
                for i, char in enumerate(label):
                    col = lx + i
                    if 0 <= col < plot_w and grid_z[sy_coord][col] < 900.0:
                        grid_char[sy_coord][col] = char
                        grid_style[sy_coord][col] = label_style
                        grid_z[sy_coord][col] = 400.0

        # 5. Assemble Rich Text Renderable
        t = Text()

        # Canvas Header Banner
        t.append("╭─ ", style=COLOR_TEXT_DIM)
        t.append("3D NEURAL TOPOLOGY GRAPH ", style=f"bold {COLOR_CYAN}")
        t.append("── ", style=COLOR_TEXT_DIM)
        t.append("LIVE BRAILLE / ASCII ORBIT ", style=f"bold {COLOR_EMERALD}")
        rem_title = max(0, plot_w - 48)
        t.append("─" * rem_title, style=COLOR_TEXT_DIM)
        t.append("╮\n", style=COLOR_TEXT_DIM)

        # Meta Metrics Subtitle
        rot_status = "AUTO-ORBIT" if self.auto_rotate else "MANUAL HOLD"
        t.append("│ ", style=COLOR_TEXT_DIM)
        t.append(f"NODES: {len(TOPOLOGY_NODES)} ", style=f"bold {COLOR_EMERALD}")
        t.append("│ ", style=COLOR_TEXT_DIM)
        t.append(f"EDGES: {len(TOPOLOGY_EDGES)} ", style=f"bold {COLOR_CYAN}")
        t.append("│ ", style=COLOR_TEXT_DIM)
        t.append(f"YAW: {math.degrees(self.yaw):.0f}° ", style=COLOR_TEXT_MUTED)
        t.append(f"PITCH: {math.degrees(self.pitch):.0f}° ", style=COLOR_TEXT_MUTED)
        t.append("│ ", style=COLOR_TEXT_DIM)
        t.append(f"{rot_status} ", style=f"bold #f59e0b" if not self.auto_rotate else f"dim {COLOR_EMERALD}")
        rem_sub = max(0, plot_w - 58)
        t.append(" " * rem_sub)
        t.append("│\n", style=COLOR_TEXT_DIM)

        # Canvas Plot Body
        for y in range(plot_h):
            t.append("│", style=COLOR_TEXT_DIM)
            curr_style = ""
            run_text = ""
            for x in range(plot_w - 2):
                ch = grid_char[y][x]
                st = grid_style[y][x]
                if st == curr_style:
                    run_text += ch
                else:
                    if run_text:
                        t.append(run_text, style=curr_style or COLOR_TEXT)
                    run_text = ch
                    curr_style = st
            if run_text:
                t.append(run_text, style=curr_style or COLOR_TEXT)
            t.append("│\n", style=COLOR_TEXT_DIM)

        # Canvas Footer & Interactive Controls Bar
        t.append("╰─ ", style=COLOR_TEXT_DIM)
        t.append("[F2] Command Center ", style=f"bold {COLOR_CYAN}")
        t.append("│ ", style=COLOR_TEXT_DIM)
        t.append("[←/→/↑/↓] Rotate ", style=f"bold {COLOR_EMERALD}")
        t.append("│ ", style=COLOR_TEXT_DIM)
        t.append("[Space] Toggle Orbit ", style="bold #f59e0b")
        rem_foot = max(0, plot_w - 58)
        t.append("─" * rem_foot, style=COLOR_TEXT_DIM)
        t.append("╯", style=COLOR_TEXT_DIM)

        return t
