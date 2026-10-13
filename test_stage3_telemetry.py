"""
test_stage3_telemetry.py
Unit and Integration Tests for Stage 3:
1. Micro-sparkline generator boundary verification.
2. Non-blocking telemetry collector and snapshot structure.
3. Live throughput sparkline recording.
4. AgentStateHUD render verification.
5. Visual UI sanitization audit (verifies zero occurrences of "zara" in tui/ widgets).
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tui.telemetry import (
    make_sparkline,
    record_throughput_sample,
    record_vram_sample,
    get_throughput_sparkline,
    poll_hardware_telemetry,
    get_cached_telemetry,
    TelemetrySnapshot,
)
from tui.widgets import AgentStateHUD, InputWell, ChatLog


class TestStage3Telemetry(unittest.TestCase):
    """Test suite for Stage 3 telemetry, sparklines, and visual sanitization."""

    def test_01_sparkline_generator_levels(self):
        """Verify make_sparkline accurately maps numeric levels to block characters."""
        # Empty input pads to requested length
        self.assertEqual(make_sparkline([], length=8), "        ")

        # Ramping series from 0 to 7
        ramp = make_sparkline([0, 1, 2, 3, 4, 5, 6, 7], min_val=0, max_val=7, length=8)
        self.assertEqual(ramp, " ▂▃▄▅▆▇█")

        # Clamping above max_val
        over = make_sparkline([100.0] * 8, min_val=0, max_val=50.0, length=8)
        self.assertEqual(over, "████████")

        # Clamping below min_val
        under = make_sparkline([-10.0] * 8, min_val=0, max_val=50.0, length=8)
        self.assertEqual(under, "        ")

    def test_02_throughput_recording_and_sparkline(self):
        """Verify throughput samples update the sparkline dynamically."""
        record_throughput_sample(5.0)
        record_throughput_sample(15.0)
        record_throughput_sample(30.0)
        sp = get_throughput_sparkline(length=8)
        self.assertEqual(len(sp), 8)
        self.assertTrue(sp.endswith("█"))

    def test_03_telemetry_snapshot_structure(self):
        """Verify poll_hardware_telemetry returns complete real hardware snapshot."""
        snapshot = poll_hardware_telemetry()
        self.assertIsInstance(snapshot, TelemetrySnapshot)
        self.assertIn("%", snapshot.cpu)
        self.assertIn("GB", snapshot.ram)
        self.assertEqual(len(snapshot.cpu_sparkline), 8)
        self.assertEqual(len(snapshot.vram_sparkline), 8)
        self.assertGreater(snapshot.context_budget, 0)

        # Verify cached snapshot matches
        cached = get_cached_telemetry()
        self.assertEqual(cached.cpu, snapshot.cpu)

    def test_04_hud_renders_with_sparklines(self):
        """Verify AgentStateHUD renders micro-sparklines without error."""
        hud = AgentStateHUD()
        rendered_text = hud.render()
        raw_str = rendered_text.plain

        self.assertIn("AGENT STATE HUD", raw_str)
        self.assertIn("ACTIVE PERSONA", raw_str)
        self.assertIn("zaine-reflex-7b", raw_str)
        self.assertIn("INFERENCE & STREAM RATE", raw_str)
        self.assertIn("Throughput:", raw_str)
        self.assertIn("HARDWARE TELEMETRY", raw_str)
        self.assertIn("CPU:", raw_str)
        self.assertIn("GPU VRAM:", raw_str)

    def test_05_visual_ui_sanitization_audit(self):
        """Verify zero visual occurrences of 'zara' across all tui/ code and widgets."""
        tui_dir = PROJECT_ROOT / "tui"
        for py_file in tui_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8").lower()
            self.assertNotIn(
                "who is zara",
                content,
                f"Visual placeholder 'who is zara' still present in {py_file.name}"
            )
            self.assertNotIn(
                "vault/people/zara.md",
                content,
                f"Reference to Zara vault note present in {py_file.name}"
            )


if __name__ == "__main__":
    unittest.main()
