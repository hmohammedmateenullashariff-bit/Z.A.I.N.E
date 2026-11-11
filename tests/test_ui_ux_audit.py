"""
tests/test_ui_ux_audit.py
Targeted test suite verifying UI/UX fixes:
- No cliff hangers or cutoffs without ellipsis
- No layout wrapping issues in cards, status bars, and modal ASCII graphs
- Responsive scaling and alignment across various column widths
"""

import unittest
from rich.console import Console
from rich.text import Text
from textual.geometry import Size

import terminal_ui
from tui.widgets.hud import AgentStateHUD, _row
from tui.widgets.header import HeaderBar
from tui.widgets.footer import FooterBar
from tui.widgets.chat import AssistantTurnCard, UserTurnCard, SystemCard
from tui.widgets.tool_line import ToolLine
from tui.widgets.digraph import SunDigraphCanvas
from tui.widgets.obsidian_modal import ObsidianMemoryModal
from tui.views.topology_view import TurnSummaryCard, SystemStatusCard, _kv


class TestUIUXAudit(unittest.TestCase):

    def test_terminal_status_bar_no_wrapping_narrow(self):
        """Status bar must never wrap onto multiple lines even at narrow columns."""
        for width in (55, 65, 75, 80, 100, 120):
            c = Console(width=width, record=True, legacy_windows=False)
            orig_cols = terminal_ui.get_terminal_cols
            orig_console = terminal_ui.console
            terminal_ui.get_terminal_cols = lambda: width
            terminal_ui.console = c
            try:
                terminal_ui.state.active_model = "qwen2.5-coder:14b-instruct-q4_K_M"
                terminal_ui.render_status_bar(
                    status_text="TOOL: search_knowledge_engine_and_summarize",
                    tool_info="search_knowledge_engine_and_summarize"
                )
                output = c.export_text()
                lines = [l for l in output.splitlines() if l.strip()]
                # A single status bar panel must have exactly 3 visual lines: top border, content, bottom border
                # If it wrapped, there would be 4 or more lines
                panel_lines = [l for l in lines if any(ch in l for ch in ("┌", "│", "└", "+", "|"))]
                self.assertEqual(len(panel_lines), 3, f"Status bar wrapped into multiple rows at width={width}: {panel_lines}")
            finally:
                terminal_ui.get_terminal_cols = orig_cols
                terminal_ui.console = orig_console

    def test_format_tool_args_summary_ellipsis(self):
        """Truncated arguments must always end with ellipsis without overflowing 60 cols."""
        long_str = "a" * 80
        res = terminal_ui.format_tool_args_summary(long_str)
        self.assertTrue(res.endswith("..."), f"Expected ellipsis at end: {res}")
        self.assertLessEqual(len(res), 60, f"Exceeded limit 60: {len(res)}")

        d = {"param1": "x" * 50, "param2": "y" * 50}
        res_d = terminal_ui.format_tool_args_summary(d)
        self.assertIn("...", res_d)

    def test_hud_row_truncation_with_ellipsis(self):
        """HUD _row with max_w must truncate with ellipsis and never wrap."""
        t = Text()
        _row(t, "Model", "qwen2.5-coder:14b-instruct-q4_K_M", max_w=15)
        rendered = t.plain
        self.assertIn("…", rendered)
        val_part = rendered.split("Model")[1].strip()
        self.assertLessEqual(len(val_part), 15)

    def test_hud_recent_tools_ellipsis(self):
        """Recent tools in HUD must append ellipsis when truncated."""
        hud = AgentStateHUD()
        hud.add_tool_run("very_long_custom_tool_execution_operation_name", duration_s=1.23, status="COMPLETED")
        hud._size = Size(38, 30)
        t = hud.render()
        plain = t.plain
        self.assertIn("…", plain, "Tool name should have ellipsis in HUD when truncated")

    def test_header_and_footer_no_wrap(self):
        """Header and footer widgets must set no_wrap=True and overflow='ellipsis'."""
        h = HeaderBar()
        h._size = Size(80, 2)
        h.agent_name = "VeryLongAgentNameThatExceedsNormalWidth"
        t_h = h.render()
        self.assertTrue(t_h.no_wrap)
        self.assertEqual(t_h.overflow, "ellipsis")

        f = FooterBar()
        f._size = Size(80, 1)
        f.model = "qwen2.5-coder:14b-instruct-q4_K_M"
        t_f = f.render()
        self.assertTrue(t_f.no_wrap)
        self.assertEqual(t_f.overflow, "ellipsis")

    def test_assistant_turn_card_pipeline_header_responsive(self):
        """AssistantTurnCard digraph pipeline header must adapt to narrow widths without wrapping."""
        card = AssistantTurnCard(markdown_text="Test response", model="qwen2.5-coder:14b-instruct-q4_K_M", agent_name="visionquest")
        card._size = Size(42, 10)
        panel = card.render()
        self.assertTrue(panel.expand)

        c = Console(width=42, record=True, legacy_windows=False)
        c.print(panel)
        out = c.export_text()
        for line in out.splitlines():
            self.assertFalse(line.strip().endswith("──▶"), f"Orphan arrow dangling at line end: '{line}'")

    def test_sun_digraph_canvas_box_alignment(self):
        """Sun Digraph box layers must have exact matching border widths without bulging."""
        canvas = SunDigraphCanvas()
        canvas._size = Size(80, 30)
        mock_graph = type("MockGraph", (), {
            "is_empty": False,
            "is_active": True,
            "summary": lambda self: {
                "prompt": "Write a complete python web scraper with BeautifulSoup and requests",
                "agent": "VisionQuestSuperLongAgentName",
                "model": "qwen2.5-coder:14b-instruct",
                "tok_s": 42.5,
                "tokens": 128,
                "tools": 4,
                "hops": 2,
                "turn": 1
            }
        })()
        canvas.graph = mock_graph
        txt = canvas.build_sun_text()
        lines = txt.plain.splitlines()

        # Check Layer 1 (Prompt box lines 3-5)
        l1_lines = lines[3:6]
        self.assertEqual(len(l1_lines), 3)
        for l in l1_lines:
            self.assertEqual(len(l), 46, f"Layer 1 box border misaligned: '{l}' (len {len(l)} != 46)")

        # Check Layer 2 (Solar core box lines 8-11)
        l2_lines = lines[8:12]
        self.assertEqual(len(l2_lines), 4)
        for l in l2_lines:
            self.assertEqual(len(l), 46, f"Layer 2 box border misaligned: '{l}' (len {len(l)} != 46)")

        # Check Layer 3 (Pipeline box lines 14-17)
        l3_lines = lines[14:18]
        self.assertEqual(len(l3_lines), 4)
        for l in l3_lines:
            self.assertEqual(len(l), 46, f"Layer 3 box border misaligned: '{l}' (len {len(l)} != 46)")

        # Check Layer 4 (Output box lines 20-22)
        l4_lines = lines[20:23]
        self.assertEqual(len(l4_lines), 3)
        for l in l4_lines:
            self.assertEqual(len(l), 46, f"Layer 4 box border misaligned: '{l}' (len {len(l)} != 46)")

    def test_obsidian_modal_canvas_width_fits_80_cols(self):
        """Obsidian modal canvas ASCII graph must not exceed 70 columns."""
        modal = ObsidianMemoryModal()
        captured = []
        mock_canvas = type("MockCanvas", (), {"update": lambda self, t: captured.append(t)})()
        modal.query_one = lambda selector, *args: mock_canvas
        modal._render_graph()
        self.assertTrue(len(captured) > 0)
        t = captured[0]
        for line in t.plain.splitlines():
            self.assertLessEqual(len(line), 70, f"Obsidian ASCII line exceeds 70 cols: '{line}' ({len(line)} chars)")

    def test_topology_turn_and_system_card_kv_truncation(self):
        """_kv in topology view must truncate long values to prevent multi-line card wrapping."""
        t = Text()
        _kv(t, "Consulted", "AgentA (code), AgentB (search), AgentC (review), AgentD (deploy)", max_val_w=20)
        self.assertIn("…", t.plain)
        val = t.plain.split("Consulted")[1].strip()
        self.assertLessEqual(len(val), 20)

    def test_dashboard_demo_responsive_and_glassmorphism(self):
        """Verify DashboardDemo/index.html has clean glassmorphism, dark theme, and mobile/desktop responsiveness."""
        from pathlib import Path
        html_path = Path("generated_sites/DashboardDemo/index.html")
        self.assertTrue(html_path.exists())
        html = html_path.read_text(encoding="utf-8")

        # 1. Glassmorphism & dark theme
        self.assertIn('class="dark"', html)
        self.assertIn(".glass {", html)
        self.assertIn("backdrop-filter: blur(12px);", html)
        self.assertIn("bg-[#030712]", html)

        # 2. Fully responsive grid & container
        self.assertIn("grid-cols-1 md:grid-cols-3", html)
        self.assertIn("flex-col md:flex-row", html)
        self.assertIn("w-full md:w-64", html)

    def test_edit_video_timeline_vertical_and_loudnorm(self):
        """Verify edit_video_timeline correctly handles 9:16 vertical crop and -14 LUFS loudnorm."""
        import json
        import tools_skills
        out_raw = tools_skills.edit_video_timeline("test_shorts", "[]", format="shorts")
        data = json.loads(out_raw)
        self.assertEqual(data["loudness_target"], "-14.0 LUFS")

        pipeline = data["ffmpeg_pipeline"]
        self.assertIn("loudnorm=I=-14:LRA=7:tp=-1.0", pipeline)
        self.assertIn("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", pipeline)
        self.assertIn("-map 0:v", pipeline)
        self.assertIn("-map \"[aout]\"", pipeline)


if __name__ == "__main__":
    unittest.main()
