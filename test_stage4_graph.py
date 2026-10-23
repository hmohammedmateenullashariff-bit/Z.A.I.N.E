"""
test_stage4_graph.py
F3 graph workspace tests:
1. Orbit layout + 3D projection of a real-shaped system graph stay within sane bounds.
2. Orbit canvas renders its title, braille glyphs and controls; empty state when no graph.
3. Interactive rotation controls.
4. Turn summary, system status and event stream cards render real data or honest empty states.
5. F3 toggles workspaces; 1/2/3 switch graph modes; focus returns to the prompt.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from textual.widgets import Input, ContentSwitcher
from tui.app import ZaineTUI
from tui.widgets import HeaderBar, NeuralGraph3D, TopologyWorkspace
from tui.widgets.graph_3d import layout_orbit
from tui.views.topology_view import TurnSummaryCard, SystemStatusCard, EventStreamPanel
from tui.system_graph import SystemGraph
from tui.exec_graph import ExecGraph


def sample_system_graph() -> SystemGraph:
    g = SystemGraph()
    g.add("core", "service", "Core Service", ":7860 ready", "online")
    g.add("router", "group", "Router", "Ollama", "online", parent="core")
    for m in ("zaine-fast-3b", "zaine-reflex-7b", "moondream"):
        g.add(f"model:{m}", "llm", m, "1.8G disk", "idle", parent="router")
    g.add("agent", "group", "Agent", "119 clustered tools", "online", parent="core")
    for c in ("SYSTEM", "DEV_CODE"):
        g.add(f"cluster:{c}", "cluster", c, "24 tools", "ok", parent="agent")
    g.add("guard", "group", "Guardrail", "0 pending", "online", parent="core")
    g.facts = {"core_up": True, "core_status": {"port": 7860, "model_loaded": True, "mode": "jarvis"},
               "ollama_up": True, "loaded_models": [("zaine-fast-3b", 2.2)], "pending_approvals": 0,
               "telegram_online": True}
    return g


class TestStage4Graph(unittest.IsolatedAsyncioTestCase):

    def test_01_orbit_layout_and_projection(self):
        nodes, edges = layout_orbit(sample_system_graph())
        self.assertEqual(len(nodes), 9)
        self.assertEqual(len(edges), 8)
        root = next(n for n in nodes if n.node_id == "core")
        self.assertEqual(root.pos3d, (0.0, 0.0, 0.0))
        graph = NeuralGraph3D()
        graph.nodes3d, graph.edges3d = nodes, edges
        w, h = 80, 24
        projected = graph.project_nodes(w, h)
        self.assertEqual(set(projected), {n.node_id for n in nodes})
        for sx, sy, z in projected.values():
            self.assertIsInstance(sx, int)
            self.assertIsInstance(sy, int)
            self.assertGreater(sx, -20)
            self.assertLess(sx, w + 20)
            self.assertGreater(sy, -15)
            self.assertLess(sy, h + 15)
            self.assertGreater(z, -6.0)
            self.assertLess(z, 6.0)

    def test_02_orbit_render_structure(self):
        graph = NeuralGraph3D()
        raw_empty = graph.render().plain
        self.assertIn("3D SYSTEM ORBIT", raw_empty)
        self.assertIn("not collected yet", raw_empty)

        graph.nodes3d, graph.edges3d = layout_orbit(sample_system_graph())
        raw = graph.render().plain
        self.assertIn("9 nodes", raw)
        self.assertIn("[←/→/↑/↓] Rotate", raw)
        self.assertIn("[Space] Hold/Orbit", raw)
        self.assertTrue(any(c in raw for c in ["⣿", "⣶", "⠶", "·", "."]))
        self.assertIn("Core Service", raw)

    def test_03_interactive_rotation_controls(self):
        graph = NeuralGraph3D()
        initial_yaw, initial_pitch = graph.yaw, graph.pitch
        graph.action_rotate_right()
        self.assertNotEqual(graph.yaw, initial_yaw)
        graph.action_pitch_up()
        self.assertNotEqual(graph.pitch, initial_pitch)
        self.assertTrue(graph.auto_rotate)
        graph.action_toggle_auto_rotate()
        self.assertFalse(graph.auto_rotate)

    def test_04_cards_render_real_data_or_empty_states(self):
        turn = TurnSummaryCard()
        self.assertIn("No turn yet", turn.render().plain)
        g = ExecGraph()
        g.start_turn("hello")
        g.apply({"type": "tool_event", "stage": "route", "data": {"tier": "REFLEX", "model": "zaine-fast-3b"}})
        g.apply({"type": "tool_event", "stage": "profiler", "data": {"model": "zaine-fast-3b", "eval_count": 40, "eval_duration_s": 1.0}})
        g.apply({"type": "done", "reply": "Hi Sir"})
        turn.graph = g
        raw = turn.render().plain
        self.assertIn("DONE", raw)
        self.assertIn("40 @ 40.0 tok/s", raw)

        status = SystemStatusCard()
        self.assertIn("Collecting", status.render().plain)
        status.facts = sample_system_graph().facts
        sraw = status.render().plain
        self.assertIn("online :7860", sraw)
        self.assertIn("zaine-fast-3b 2.2G", sraw)
        self.assertIn("poller online", sraw)

        bus = EventStreamPanel()
        self.assertIn("Waiting for the first turn", bus.render().plain)
        bus.graph = g
        self.assertIn("ROUTER", bus.render().plain)

    async def test_05_f3_toggle_and_mode_keys(self):
        app = ZaineTUI()
        async with app.run_test(size=(160, 45)) as pilot:
            chat_ws = app.query_one("#chat-workspace")
            topo_ws = app.query_one(TopologyWorkspace)
            header = app.query_one(HeaderBar)
            self.assertTrue(chat_ws.display)
            self.assertFalse(topo_ws.display)
            self.assertIn("VIEW: COMMAND", header.render().plain)

            await pilot.press("f3")
            await pilot.pause(0.05)
            self.assertFalse(chat_ws.display)
            self.assertTrue(topo_ws.display)
            self.assertIn("VIEW: GRAPH", header.render().plain)

            switcher = topo_ws.query_one(ContentSwitcher)
            self.assertEqual(switcher.current, "exec")
            await pilot.press("2")
            await pilot.pause(0.05)
            self.assertEqual(switcher.current, "system")
            await pilot.press("3")
            await pilot.pause(0.05)
            self.assertEqual(switcher.current, "orbit")
            await pilot.press("1")
            await pilot.pause(0.05)
            self.assertEqual(switcher.current, "exec")

            await pilot.press("f3")
            await pilot.pause(0.05)
            self.assertTrue(chat_ws.display)
            self.assertIn("VIEW: COMMAND", header.render().plain)
            self.assertTrue(app.query_one("#user-input", Input).has_focus)


if __name__ == "__main__":
    unittest.main()
