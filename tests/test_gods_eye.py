"""
tests/test_gods_eye.py
Unit and integration tests for tactical.gods_eye_bridge and F.R.I.D.A.Y.'s TACTICAL_OSINT cluster.
Verifies:
- Live/fallback ADS-B airspace query
- Orbital satellite telemetry retrieval (ISS 25544)
- Real-time USGS earthquake sensor feeds
- Local sentinel status and tactical overview synthesis
- TOOL_REGISTRY integration
"""

import unittest
from tools import TOOL_REGISTRY
from tactical.gods_eye_bridge import (
    query_air_traffic,
    get_satellite_pass,
    get_seismic_hazards,
    get_local_tactical_status,
    get_tactical_overview
)


class TestGodsEyeTactical(unittest.TestCase):
    def test_01_query_air_traffic(self):
        """Verify OpenSky ADS-B transponder query returns structured schema."""
        res = query_air_traffic(lat=12.9716, lon=77.5946, radius_deg=1.5)
        self.assertIn(res["status"], ("ok", "fallback"))
        self.assertIn("aircraft_count", res)
        self.assertIn("summary", res)
        self.assertIsInstance(res["aircraft"], list)

    def test_02_get_satellite_pass(self):
        """Verify orbital telemetry retrieval for ISS (NORAD 25544)."""
        res = get_satellite_pass(25544)
        self.assertIn(res["status"], ("ok", "fallback"))
        self.assertIn("satellite", res)
        self.assertIn("period_minutes", res)
        self.assertTrue(res["period_minutes"] > 0)

    def test_03_get_seismic_hazards(self):
        """Verify USGS earthquake monitoring feed."""
        res = get_seismic_hazards(min_magnitude=4.5)
        self.assertEqual(res["status"], "ok")
        self.assertIn("hazard_count", res)
        self.assertIn("summary", res)

    def test_04_local_tactical_status(self):
        """Verify local sentinel hardware mutex and operator check."""
        res = get_local_tactical_status()
        self.assertEqual(res["status"], "ok")
        self.assertIn("camera_in_use", res)
        self.assertIn("operator", res)

    def test_05_tactical_overview_synthesis(self):
        """Verify F.R.I.D.A.Y. executive situation report synthesis."""
        overview = get_tactical_overview()
        self.assertTrue(len(overview) > 50)
        self.assertIn("F.R.I.D.A.Y. GOD'S EYE", overview)
        self.assertIn("LOCAL SENTINEL", overview)

    def test_06_tool_registry_mounting(self):
        """Verify all God's Eye tools are properly mounted and callable in TOOL_REGISTRY."""
        for tool_name in ["tactical_overview", "query_air_traffic", "get_satellite_pass", "get_seismic_hazards", "get_local_tactical_status"]:
            self.assertIn(tool_name, TOOL_REGISTRY, f"Tool '{tool_name}' missing from TOOL_REGISTRY")
            fn = TOOL_REGISTRY[tool_name]
            self.assertTrue(callable(fn), f"Tool '{tool_name}' is not callable")


if __name__ == "__main__":
    unittest.main()

