"""
tests/test_hud_state_reducer.py
Unit tests verifying the Living Arc Reactor HUD state reducer and atomic SSE event delivery.
"""

import json
import unittest
from satellite_hud.state_reducer import hud_state_reducer


class TestHudStateReducer(unittest.TestCase):
    def test_01_atomic_dispatch(self):
        new_state = hud_state_reducer.dispatch(
            "TELEMETRY_UPDATE",
            {"vram_used_mb": 2150.0, "tokens_per_sec": 42.5}
        )
        self.assertEqual(new_state["vram_used_mb"], 2150.0)
        self.assertEqual(new_state["tokens_per_sec"], 42.5)

    def test_02_breaker_reflection_trigger(self):
        new_state = hud_state_reducer.dispatch(
            "BREAKER_TRANSITION",
            {"state": "OPEN"}
        )
        self.assertEqual(new_state["breaker_state"], "OPEN")
        self.assertEqual(new_state["system_status"], "REFLECTING")

        reset_state = hud_state_reducer.dispatch(
            "BREAKER_TRANSITION",
            {"state": "CLOSED"}
        )
        self.assertEqual(reset_state["breaker_state"], "CLOSED")
        self.assertEqual(reset_state["system_status"], "HEALTHY")

    def test_03_sse_subscriber_lifecycle(self):
        q = hud_state_reducer.register_subscriber()
        initial_msg = q.get_nowait()
        self.assertTrue(initial_msg.startswith("data: "))

        hud_state_reducer.dispatch("AGENT_SWITCH", {"agent_id": "edith"})
        event_msg = q.get_nowait()
        data = json.loads(event_msg.replace("data: ", "").strip())
        self.assertEqual(data["active_subagent"], "edith")

        hud_state_reducer.unregister_subscriber(q)


if __name__ == "__main__":
    unittest.main()

