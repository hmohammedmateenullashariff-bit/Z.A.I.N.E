"""
test_tool_dispatch.py
1. get_datetime answers for cities, countries and IANA zones, and reports unknown places honestly.
2. The agent drops arguments a tool does not accept (a common local-LLM mistake) and tells the model,
   instead of failing the whole call with a TypeError.
3. scripts/ensure_core.py detects a core running with different settings.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent
for p in (PROJECT_ROOT, PROJECT_ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import tools
import ensure_core


class TestGetDatetime(unittest.TestCase):

    def test_local_only(self):
        out = tools.get_datetime()
        self.assertTrue(out.startswith("Local: "))
        self.assertEqual(len(out.splitlines()), 1)

    def test_locations(self):
        out = tools.get_datetime(location="Dubai", locations=["india", "Europe/London", "Atlantis"])
        self.assertIn("Dubai (Asia/Dubai)", out)
        self.assertIn("UTC+04:00", out)
        self.assertIn("india (Asia/Kolkata)", out)
        self.assertIn("Europe/London (Europe/London)", out)
        self.assertIn("Atlantis: unknown location", out)


class TestArgumentFiltering(unittest.TestCase):

    def setUp(self):
        import agent
        self.agent = agent.ZaineAgent.__new__(agent.ZaineAgent)  # no model pinning needed
        self.patch = patch("face_id.get_active_user", return_value={"name": "t", "role": "admin"})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_unknown_argument_is_dropped_and_reported(self):
        out = self.agent._execute_tool({"tool": "get_datetime", "args": {"location": "Dubai", "verbose": True}})
        self.assertIn("Asia/Dubai", out)
        self.assertIn("ignored unsupported argument(s) for get_datetime: verbose", out)
        self.assertNotIn("Error running tool", out)

    def test_missing_required_argument_still_errors(self):
        with patch.dict(tools.TOOL_REGISTRY, {"needs_x": lambda_needs_x}):
            out = self.agent._execute_tool({"tool": "needs_x", "args": {}})
        self.assertIn("Error running tool 'needs_x'", out)


def lambda_needs_x(x):
    return x


class TestEnsureCore(unittest.TestCase):

    def test_differences(self):
        wanted = {"fast": True, "demo": True, "single_model": True, "num_ctx": 6144, "workspace": r"C:\a\demo_workspace"}
        running = {"fast": False, "demo": True, "single_model": True, "num_ctx": 6144, "workspace": "C:/a/demo_workspace"}
        diffs = ensure_core.differences(running, wanted)
        self.assertEqual(len(diffs), 1)
        self.assertIn("fast", diffs[0])
        self.assertEqual(ensure_core.differences(dict(wanted), wanted), [])
        self.assertEqual(len(ensure_core.differences({}, wanted)), 5)  # old core without config


if __name__ == "__main__":
    unittest.main()
