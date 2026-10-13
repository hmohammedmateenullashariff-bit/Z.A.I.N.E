"""
test_stage4_graph.py
Stage 4 Unit and Textual Pilot Integration Tests:
1. 3D coordinate projection math outputs valid terminal coordinates.
2. 3D Braille/ASCII Canvas render structure and symbols.
3. F2 key press switches active visible workspace container in Textual pilot (#chat-workspace <-> #topology-workspace).
4. Restores focus to #user-input upon returning to Command Center.
5. Topology cards and Neural Bus render verification.
6. Interactive rotation controls.
"""

import sys
import unittest
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from textual.widgets import Input
from tui.app import ZaineTUI
from tui.widgets import (
    HeaderBar,
    NeuralGraph3D,
    TopologyWorkspace,
    ChatLog,
)
from tui.views.topology_view import (
    SwarmGovernanceCard,
    MemoryTopologyCard,
    ClusterSpecCard,
    NeuralBusPanel,
)
from tui.widgets.graph_3d import TOPOLOGY_NODES, TOPOLOGY_EDGES


class TestStage4Graph(unittest.IsolatedAsyncioTestCase):
    """Test suite for Stage 4 3D Neural Node Graph and Workspace Toggling."""

    def test_01_3d_projection_math(self):
        """Verify 3D coordinate projection math outputs valid, bounded terminal coordinates."""
        graph = NeuralGraph3D()
        w, h = 80, 24
        projected = graph.project_nodes(w, h)

        # Check all nodes in topology are present
        self.assertEqual(len(projected), len(TOPOLOGY_NODES))
        for node in TOPOLOGY_NODES:
            self.assertIn(node.node_id, projected)
            sx, sy, z = projected[node.node_id]
            self.assertIsInstance(sx, int)
            self.assertIsInstance(sy, int)
            self.assertIsInstance(z, float)
            # Screen coordinates should be comfortably within canvas bounds
            self.assertGreater(sx, -20)
            self.assertLess(sx, w + 20)
            self.assertGreater(sy, -15)
            self.assertLess(sy, h + 15)
            # Z depth should be within realistic perspective bounds
            self.assertGreater(z, -4.0)
            self.assertLess(z, 4.0)

    def test_02_canvas_render_structure(self):
        """Verify NeuralGraph3D renders title banner, Braille symbols, and controls."""
        graph = NeuralGraph3D()
        rendered_text = graph.render()
        raw = rendered_text.plain

        self.assertIn("3D NEURAL TOPOLOGY GRAPH", raw)
        self.assertIn("LIVE BRAILLE / ASCII ORBIT", raw)
        self.assertIn("[F2] Command Center", raw)
        self.assertIn("[←/→/↑/↓] Rotate", raw)
        self.assertIn("[Space] Toggle Orbit", raw)
        # Check presence of Braille/ASCII characters
        has_braille_or_ascii = any(c in raw for c in ["⣿", "⣶", "⠶", "·", "."])
        self.assertTrue(has_braille_or_ascii)

    def test_03_interactive_rotation_controls(self):
        """Verify action bindings alter Euler rotation angles and auto-rotate state."""
        graph = NeuralGraph3D()
        initial_yaw = graph.yaw
        initial_pitch = graph.pitch

        graph.action_rotate_right()
        self.assertNotEqual(graph.yaw, initial_yaw)

        graph.action_pitch_up()
        self.assertNotEqual(graph.pitch, initial_pitch)

        self.assertTrue(graph.auto_rotate)
        graph.action_toggle_auto_rotate()
        self.assertFalse(graph.auto_rotate)
        graph.action_toggle_auto_rotate()
        self.assertTrue(graph.auto_rotate)

    def test_04_topology_cards_and_neural_bus_render(self):
        """Verify all right sidebar topology cards and neural bus render without errors."""
        gov_card = SwarmGovernanceCard()
        gov_raw = gov_card.render().plain
        self.assertIn("SWARM GOVERNANCE & CONSENSUS", gov_raw)
        self.assertIn("100% SYNCHRONIZED", gov_raw)

        mem_card = MemoryTopologyCard()
        mem_raw = mem_card.render().plain
        self.assertIn("OBSIDIAN MEMORY TOPOLOGY", mem_raw)
        self.assertIn("Context Limit", mem_raw)

        cluster_card = ClusterSpecCard()
        cluster_raw = cluster_card.render().plain
        self.assertIn("NEURAL COMPUTE CLUSTER", cluster_raw)
        self.assertIn("NVIDIA RTX 2050", cluster_raw)

        bus_panel = NeuralBusPanel()
        bus_raw = bus_panel.render().plain
        self.assertIn("INTER-AGENT NEURAL BUS", bus_raw)

    async def test_05_f2_workspace_toggle_pilot(self):
        """Verify pressing F2 toggles workspaces and updates header status in Textual pilot."""
        app = ZaineTUI()
        async with app.run_test(size=(140, 45)) as pilot:
            chat_ws = app.query_one("#chat-workspace")
            topo_ws = app.query_one("#topology-workspace")
            header = app.query_one(HeaderBar)

            # 1. Initial State: Chat Workspace is active
            self.assertTrue(chat_ws.display)
            self.assertFalse(topo_ws.display)
            self.assertEqual(header.view_mode, "COMMAND")
            self.assertIn("VIEW: COMMAND", header.render().plain)

            # 2. Press F2: Switch to 3D Topology Workspace
            await pilot.press("f2")
            await pilot.pause(0.05)

            self.assertFalse(chat_ws.display)
            self.assertTrue(topo_ws.display)
            self.assertEqual(header.view_mode, "3D TOPOLOGY")
            self.assertIn("VIEW: 3D TOPOLOGY", header.render().plain)

            # 3. Press F2 again: Switch back to Chat Workspace
            await pilot.press("f2")
            await pilot.pause(0.05)

            self.assertTrue(chat_ws.display)
            self.assertFalse(topo_ws.display)
            self.assertEqual(header.view_mode, "COMMAND")
            self.assertIn("VIEW: COMMAND", header.render().plain)

            # 4. Verify input well is focused upon return
            input_box = app.query_one("#user-input", Input)
            self.assertTrue(input_box.has_focus)


if __name__ == "__main__":
    unittest.main()
