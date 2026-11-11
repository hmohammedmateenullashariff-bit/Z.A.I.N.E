"""
tests/test_dom_and_scrolling.py
DOM Check and Scrolling Validation Suite for Z.A.I.N.E TUI.
Verifies:
1. Full DOM tree integrity across Chat Workspace and Topology Workspace.
2. ChatLog scrollability, can_focus=True, and PageUp/PageDown/Mouse handlers.
3. SunDigraphCanvas hierarchy (VerticalScroll container + #sun-body Static), focus, and scrollability.
4. InputWell sanitization against SGR mouse escape sequences (e.g. [<65;46;13M).
5. Global scroll actions and workspace switching.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from textual.widgets import Input, ContentSwitcher, Static
from textual.containers import VerticalScroll
from tui.app import ZaineTUI
from tui.widgets import HeaderBar, FooterBar, AgentStateHUD, ChatLog, InputWell, TopologyWorkspace
from tui.widgets.digraph import SunDigraphCanvas
from tui.views.topology_view import GraphTabs


class TestDomAndScrolling(unittest.IsolatedAsyncioTestCase):

    async def test_01_dom_hierarchy_and_containment(self):
        """DOM Check: Verify core workspaces, widgets, and layout hierarchy."""
        app = ZaineTUI()
        async with app.run_test(size=(160, 45)) as pilot:
            # 1. Header & Footer
            header = app.query_one(HeaderBar)
            footer = app.query_one(FooterBar)
            self.assertIsNotNone(header)
            self.assertIsNotNone(footer)

            # 2. Chat Workspace DOM Tree
            chat_ws = app.query_one("#chat-workspace")
            self.assertTrue(chat_ws.display)
            chat_container = app.query_one("#chat-container")
            self.assertIn(chat_container, chat_ws.children)

            chat_log = app.query_one(ChatLog)
            input_well = app.query_one(InputWell)
            hud = app.query_one(AgentStateHUD)
            self.assertIn(chat_log, chat_container.children)
            self.assertIn(input_well, chat_container.children)
            self.assertIn(hud, chat_ws.children)

            # 3. Topology Workspace DOM Tree
            topo_ws = app.query_one(TopologyWorkspace)
            self.assertIsNotNone(topo_ws)
            self.assertFalse(topo_ws.display)  # Hidden initially until F3

            switcher = topo_ws.query_one(ContentSwitcher)
            self.assertIsNotNone(switcher)
            sun_canvas = topo_ws.query_one("#sun", SunDigraphCanvas)
            self.assertIsNotNone(sun_canvas)
            self.assertIn(sun_canvas, switcher.children)

    async def test_02_chat_log_scrollability_and_actions(self):
        """DOM & Scrolling Check: Ensure ChatLog scrolls vertically and accepts page scroll actions."""
        app = ZaineTUI()
        async with app.run_test(size=(120, 30)) as pilot:
            chat_log = app.query_one(ChatLog)
            self.assertTrue(issubclass(ChatLog, VerticalScroll))
            self.assertTrue(chat_log.can_focus)

            # Add multiple dummy messages to populate scroll history
            for i in range(25):
                chat_log.add_assistant_message(f"Turn #{i}: Diagnostic output stream content for scroll testing.")

            await pilot.pause(0.05)
            # Verify virtual content height exceeds visible height
            self.assertGreater(chat_log.virtual_size.height, chat_log.size.height)

            # Test keyboard / action page scrolling
            app.action_scroll_to_home()
            await pilot.pause(0.05)
            self.assertEqual(chat_log.scroll_offset.y, 0)

            app.action_scroll_page_down()
            await pilot.pause(0.05)
            self.assertGreater(chat_log.scroll_offset.y, 0)

            app.action_scroll_page_up()
            await pilot.pause(0.05)
            self.assertEqual(chat_log.scroll_offset.y, 0)

            app.action_scroll_to_end()
            await pilot.pause(0.05)
            self.assertGreater(chat_log.scroll_offset.y, 0)

    async def test_03_sun_digraph_scrollability(self):
        """DOM Check: SunDigraphCanvas is a VerticalScroll with #sun-body Static child and scroll bindings."""
        app = ZaineTUI()
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.press("f3")  # Switch to graph workspace
            await pilot.pause(0.05)

            topo_ws = app.query_one(TopologyWorkspace)
            self.assertTrue(topo_ws.display)

            await pilot.press("4")  # Mode [4] Sun Digraph
            await pilot.pause(0.05)

            switcher = topo_ws.query_one(ContentSwitcher)
            self.assertEqual(switcher.current, "sun")

            sun = topo_ws.query_one("#sun", SunDigraphCanvas)
            self.assertTrue(issubclass(SunDigraphCanvas, VerticalScroll))
            self.assertTrue(sun.can_focus)

            # Check that child #sun-body exists in DOM
            sun_body = sun.query_one("#sun-body", Static)
            self.assertIsNotNone(sun_body)

            # Trigger scroll actions
            app.action_scroll_line_down()
            await pilot.pause(0.05)
            app.action_scroll_line_up()
            await pilot.pause(0.05)
            app.action_scroll_to_home()
            await pilot.pause(0.05)

    async def test_04_input_well_mouse_escape_sanitization(self):
        """Bug Check: Verify raw ANSI / SGR mouse escape sequences are stripped from user-input."""
        app = ZaineTUI()
        async with app.run_test(size=(120, 30)) as pilot:
            inp = app.query_one("#user-input", Input)
            inp.focus()

            # Simulate mouse wheel leakage: [<65;46;13M
            inp.value = "hello [<65;46;13M world"
            await pilot.pause(0.05)
            self.assertEqual(inp.value, "hello  world")

            # Simulate PowerShell mouse tracking dump: [555;38;36M
            inp.value = "[555;38;36Mtest command"
            await pilot.pause(0.05)
            self.assertEqual(inp.value, "test command")


if __name__ == "__main__":
    unittest.main()

