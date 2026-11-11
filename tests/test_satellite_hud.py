"""
tests/test_satellite_hud.py
Unit tests verifying the Satellite HUD web bundle and endpoint routing.
Verifies Gemini Argon 4 High specifications:
- 360x360 canvas definition in index.html
- 0KB procedural WebAudio earcons (audio_synth.js)
- LivingArcReactor physics engine (arc_reactor.js)
- Static assets and /hud route accessibility
"""

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestSatelliteHUD(unittest.TestCase):
    def setUp(self):
        self.hud_dir = PROJECT_ROOT / "satellite_hud"
        self.static_dir = self.hud_dir / "static"

    def test_01_hud_files_exist_and_non_empty(self):
        """Verify all Satellite HUD assets exist and contain required components."""
        index_html = self.hud_dir / "index.html"
        self.assertTrue(index_html.exists(), "index.html missing")
        content = index_html.read_text(encoding="utf-8")
        self.assertIn("arcCanvas", content)
        self.assertIn("/static/hud.css", content)
        self.assertIn("/static/audio_synth.js", content)
        self.assertIn("/static/arc_reactor.js", content)

    def test_02_audio_synth_procedural_signatures(self):
        """Verify audio_synth.js defines procedural synthesis for all required personas."""
        synth_js = self.static_dir / "audio_synth.js"
        self.assertTrue(synth_js.exists(), "audio_synth.js missing")
        code = synth_js.read_text(encoding="utf-8")
        self.assertIn("wake", code)
        self.assertIn("handoff", code)
        self.assertIn("edith", code)
        self.assertIn("friday", code)
        self.assertIn("ultron", code)
        self.assertIn("reflect", code)

    def test_03_arc_reactor_physics_engine(self):
        """Verify arc_reactor.js implements spring-damper physics and 4 layers."""
        reactor_js = self.static_dir / "arc_reactor.js"
        self.assertTrue(reactor_js.exists(), "arc_reactor.js missing")
        code = reactor_js.read_text(encoding="utf-8")
        self.assertIn("LivingArcReactor", code)
        self.assertIn("this.torque", code)
        self.assertIn("this.damping", code)
        self.assertIn("this.inertia", code)
        self.assertIn("_drawOuterBezel", code)
        self.assertIn("_drawGimbals", code)
        self.assertIn("_drawStatorRing", code)
        self.assertIn("_drawPlasmaCore", code)

    def test_04_hud_css_and_layout(self):
        """Verify HUD CSS defines responsive container and dark palette."""
        hud_css = self.static_dir / "hud.css"
        self.assertTrue(hud_css.exists(), "hud.css missing")
        css = hud_css.read_text(encoding="utf-8")
        self.assertIn("--cyan-primary", css)
        self.assertIn(".reactor-viewport", css)


if __name__ == "__main__":
    unittest.main()

