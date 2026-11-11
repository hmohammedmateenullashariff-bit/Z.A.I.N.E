"""
tests/test_circuit_breaker_and_envelopes.py
Unit and acceptance tests for:
1. core.circuit_breaker (CircuitBreakerManager, states CLOSED -> OPEN -> HALF_OPEN -> CLOSED, backoff)
2. core.task_envelope (TaskEnvelope, ResultEnvelope, ContextVar permission gating)
"""

import time
import unittest

from core.circuit_breaker import CircuitBreakerManager, CircuitState
from core.task_envelope import (
    TaskEnvelope,
    ResultEnvelope,
    is_tool_permitted,
    current_agent_var,
    current_envelope_var
)


class TestCircuitBreakerAndEnvelopes(unittest.TestCase):
    def setUp(self):
        self.breaker_mgr = CircuitBreakerManager(
            failure_threshold=3,
            window_seconds=10.0,
            base_cooldown_seconds=0.5,  # Short for fast testing
            max_cooldown_seconds=5.0
        )
        self.breaker_mgr.reset()

    def test_01_closed_to_open_transition(self):
        """Verify 3 failures within window trip the breaker to OPEN."""
        tool = "weather_api"
        target = "api.weather.com"

        # Initially allowed
        allowed, _ = self.breaker_mgr.can_execute(tool, target)
        self.assertTrue(allowed)

        # 1st failure
        state, _ = self.breaker_mgr.record_failure(tool, "HTTP500", "Server Error", target=target)
        self.assertEqual(state, CircuitState.CLOSED)

        # 2nd failure
        state, _ = self.breaker_mgr.record_failure(tool, "HTTP500", "Server Error", target=target)
        self.assertEqual(state, CircuitState.CLOSED)

        # 3rd failure -> trips OPEN
        state, _ = self.breaker_mgr.record_failure(tool, "HTTP500", "Server Error", target=target)
        self.assertEqual(state, CircuitState.OPEN)

        # Immediate next check should be BLOCKED
        allowed, reason = self.breaker_mgr.can_execute(tool, target)
        self.assertFalse(allowed)
        self.assertIn("UNAVAILABLE", reason)

    def test_02_half_open_probe_success(self):
        """Verify cooldown expiration leads to HALF_OPEN, and success closes it."""
        tool = "payment_gateway"
        for _ in range(3):
            self.breaker_mgr.record_failure(tool, "Timeout", "Gateway timed out")

        # Confirm OPEN
        allowed, _ = self.breaker_mgr.can_execute(tool)
        self.assertFalse(allowed)

        # Wait for cooldown (0.5s)
        time.sleep(0.6)

        # Next call should be allowed as probe in HALF_OPEN
        allowed, _ = self.breaker_mgr.can_execute(tool)
        self.assertTrue(allowed)

        # Record probe success -> should reset to CLOSED
        self.breaker_mgr.record_success(tool)
        status = self.breaker_mgr.get_breaker_status(tool)
        self.assertEqual(status["state"], CircuitState.CLOSED.value)

    def test_03_half_open_probe_failure_doubles_cooldown(self):
        """Verify failed probe in HALF_OPEN snaps back to OPEN with doubled cooldown."""
        tool = "database_sync"
        for _ in range(3):
            self.breaker_mgr.record_failure(tool, "LockError", "Locked")

        time.sleep(0.6)  # Cooldown over -> probe allowed
        allowed, _ = self.breaker_mgr.can_execute(tool)
        self.assertTrue(allowed)

        # Probe fails
        state, _ = self.breaker_mgr.record_failure(tool, "LockError", "Still locked")
        self.assertEqual(state, CircuitState.OPEN)

        # Verify cooldown doubled to 1.0s
        status = self.breaker_mgr.get_breaker_status(tool)
        self.assertAlmostEqual(status["cooldown_s"], 1.0, delta=0.1)

    def test_04_task_envelope_validation_and_token_bounds(self):
        """Verify brief length is clipped to <= 600 chars to prevent prompt bloat."""
        oversized_brief = "A" * 800
        env = TaskEnvelope(
            goal="Refactor config parser",
            from_agent="zaine-core",
            to_agent="edith-coder",
            brief=oversized_brief,
            denied_tools=["execute_command", "install_package"]
        )
        self.assertTrue(len(env.brief) <= 600)
        self.assertTrue(env.brief.endswith("..."))

    def test_05_contextvar_tool_permission_gating(self):
        """Verify ContextVar permission enforcement denies forbidden tools."""
        env = TaskEnvelope(
            goal="Run linting",
            from_agent="zaine-core",
            to_agent="edith-coder",
            denied_tools=["execute_command", "format_hard_drive"]
        )

        token_agent = current_agent_var.set("edith-coder")
        token_env = current_envelope_var.set(env)
        try:
            # Denied tool
            permitted, reason = is_tool_permitted("execute_command")
            self.assertFalse(permitted)
            self.assertIn("explicitly denied", reason)

            # Another denied tool (case-insensitive)
            permitted2, reason2 = is_tool_permitted("FORMAT_HARD_DRIVE")
            self.assertFalse(permitted2)
            self.assertIn("explicitly denied", reason2)
        finally:
            current_agent_var.reset(token_agent)
            current_envelope_var.reset(token_env)


if __name__ == "__main__":
    unittest.main()

