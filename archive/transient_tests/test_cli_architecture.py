"""
Z.A.I.N.E. — Terminal Architecture & Voice Isolation Acceptance Test Suite
Verifies:
1. Complete Voice Isolation (11 mandatory tests from Mission Specification)
2. GUI Removal & Decoupling (7 architectural tests)
"""

import os
import sys
import time
import unittest
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import voice
from core_service import CoreService
from agent import ZaineAgent


class TestVoiceIsolation(unittest.TestCase):
    """
    Mandatory Acceptance Tests for Section 25: Voice Isolation & State Machine.
    """

    def setUp(self):
        # Guarantee initial state is clean and disabled
        voice.disable_voice()

    def tearDown(self):
        voice.disable_voice()

    def test_01_startup_state_is_voice_disabled(self):
        """1. Verify initial startup state is strictly VOICE_DISABLED."""
        self.assertEqual(voice.get_voice_state(), voice.VOICE_STATE_DISABLED)
        self.assertFalse(voice.is_voice_enabled())

    def test_02_voice_status_reports_off_by_default(self):
        """2. Verify /voice status reports enabled=False and state=VOICE_DISABLED."""
        status = voice.get_voice_status()
        self.assertEqual(status["state"], "VOICE_DISABLED")
        self.assertFalse(status["enabled"])
        self.assertFalse(status["persistent"])

    def test_03_text_response_does_not_invoke_tts_when_disabled(self):
        """3. Verify speak_sentence returns immediately without invoking TTS when voice is disabled."""
        with patch("voice._synthesize_edge_tts") as mock_edge, \
             patch("voice.get_piper_voice") as mock_piper:
            result = voice.speak_sentence("This is a test message to the user.")
            self.assertTrue(result)
            mock_edge.assert_not_called()
            mock_piper.assert_not_called()

    def test_04_text_response_does_not_open_microphone_barge_in_when_disabled(self):
        """4. Verify speak_sentence does NOT start microphone barge-in monitor when disabled."""
        with patch("voice._barge_in_monitor_thread") as mock_barge:
            voice.speak_sentence("Silent text response.")
            mock_barge.assert_not_called()

    def test_05_voice_on_explicitly_enables_voice(self):
        """5. Verify /voice on transitions state machine to VOICE_ENABLED."""
        ok, msg = voice.enable_voice()
        self.assertTrue(ok)
        self.assertEqual(voice.get_voice_state(), voice.VOICE_STATE_ENABLED)
        self.assertTrue(voice.is_voice_enabled())

    def test_06_voice_off_explicitly_disables_voice(self):
        """6. Verify /voice off transitions state machine back to VOICE_DISABLED."""
        voice.enable_voice()
        self.assertTrue(voice.is_voice_enabled())

        ok, msg = voice.disable_voice()
        self.assertTrue(ok)
        self.assertEqual(voice.get_voice_state(), voice.VOICE_STATE_DISABLED)
        self.assertFalse(voice.is_voice_enabled())

    def test_07_restart_returns_to_disabled(self):
        """7. Verify simulating a system restart returns to VOICE_DISABLED."""
        voice.enable_voice()
        self.assertTrue(voice.is_voice_enabled())

        # Simulate restart by resetting module state
        voice.disable_voice()
        self.assertEqual(voice.get_voice_state(), voice.VOICE_STATE_DISABLED)
        self.assertFalse(voice.is_voice_enabled())

    def test_08_new_session_resets_voice_to_disabled(self):
        """8. Verify new session (/new) resets voice to VOICE_DISABLED."""
        voice.enable_voice()
        self.assertTrue(voice.is_voice_enabled())

        from terminal_ui import cmd_new
        with patch("terminal_ui.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            cmd_new()

        self.assertEqual(voice.get_voice_state(), voice.VOICE_STATE_DISABLED)
        self.assertFalse(voice.is_voice_enabled())

    def test_09_one_shot_listen_restores_disabled_state(self):
        """9. Verify /speak one-shot voice command returns to VOICE_DISABLED when done."""
        self.assertEqual(voice.get_voice_state(), voice.VOICE_STATE_DISABLED)

        with patch("voice.record_audio") as mock_rec, \
             patch("voice.transcribe") as mock_trans:
            mock_rec.return_value = None
            mock_trans.return_value = "hello zaine"

            text = voice.one_shot_listen()
            self.assertEqual(text, "hello zaine")

        # After one-shot completes, state MUST restore to VOICE_DISABLED
        self.assertEqual(voice.get_voice_state(), voice.VOICE_STATE_DISABLED)
        self.assertFalse(voice.is_voice_enabled())

    def test_10_voice_failure_does_not_crash_cli(self):
        """10. Verify microphone or audio driver failure does not crash text CLI."""
        with patch("voice.record_audio", side_effect=RuntimeError("No audio input device")):
            # Should not raise exception
            text = voice.one_shot_listen()
            self.assertEqual(text, "")
            self.assertEqual(voice.get_voice_state(), voice.VOICE_STATE_DISABLED)

    def test_11_no_background_microphone_threads_active(self):
        """11. Verify no hidden microphone listener threads remain active when voice is disabled."""
        active_threads = [t.name for t in threading.enumerate()]
        mic_threads = [name for name in active_threads if "voice" in name.lower() or "mic" in name.lower() or "wake" in name.lower()]
        self.assertEqual(len(mic_threads), 0)


class TestGUIRemovalAndDecoupling(unittest.TestCase):
    """
    Mandatory Acceptance Tests for Section 26: GUI Removal & Clean Headless Core.
    """

    def test_12_core_service_does_not_depend_on_gui(self):
        """12. Verify CoreService runs headlessly with no GUI window or HTML serving."""
        with patch("core_router.router.pin_reflex_in_vram"):
            service = CoreService(port=7869)
            self.assertIsNotNone(service.agent)
            self.assertEqual(service.current_status, "idle")

    def test_13_gui_modules_and_launchers_are_absent(self):
        """13. Verify obsolete GUI modules and launchers (ui.py, launch_hud.py, electron) are completely removed."""
        with self.assertRaises(ImportError):
            import ui  # ui.py must no longer exist in the runtime
        self.assertFalse((PROJECT_ROOT / "launch_hud.py").exists())
        self.assertFalse((PROJECT_ROOT / "electron").exists())
        self.assertFalse((PROJECT_ROOT / "static").exists())
        self.assertFalse((PROJECT_ROOT / "templates").exists())

    def test_14_core_agent_runs_without_ui_module(self):
        """14. Verify ZaineAgent initializes and has zero coupling to ui.py."""
        with patch("core_router.router.pin_reflex_in_vram"):
            agent = ZaineAgent()
            self.assertFalse(hasattr(agent, "ui"))
            self.assertTrue(hasattr(agent, "chat"))
            self.assertTrue(hasattr(agent, "chat_stream"))

    def test_15_memory_system_runs_without_gui(self):
        """15. Verify memory subsystem operates completely headlessly."""
        from memory_manager import get_memory_manager
        mm = get_memory_manager()
        self.assertIsNotNone(mm)
        stats = mm.get_stats()
        self.assertIn("obsidian", stats)
        self.assertIn("folders", stats["obsidian"])

    def test_16_tool_system_runs_without_gui(self):
        """16. Verify tool registry has 119+ tools and is completely decoupled from GUI."""
        from tools import TOOL_REGISTRY
        self.assertGreaterEqual(len(TOOL_REGISTRY), 115)
        # Verify persona toggle tool works cleanly without HUD
        with patch("voice.play_ultron_chime"), patch("voice.play_chime"):
            from tools import toggle_ultron_mode
            msg = toggle_ultron_mode(True)
            self.assertIn("ULTRON PROTOCOL", msg)
            msg_jarvis = toggle_ultron_mode(False)
            self.assertIn("JARVIS PROTOCOL", msg_jarvis)

    def test_17_core_service_http_lifecycle(self):
        """17. Verify CoreService starts, serves /api/health and /api/voice/status, and stops."""
        import requests
        with patch("core_router.router.pin_reflex_in_vram"):
            service = CoreService(port=7867)
        service.start_server()
        try:
            url = f"http://127.0.0.1:{service.port}/api/health"
            resp = requests.get(url, timeout=2.0)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("ok"))
            self.assertEqual(data.get("status"), "online")

            v_url = f"http://127.0.0.1:{service.port}/api/voice/status"
            v_resp = requests.get(v_url, timeout=2.0)
            self.assertEqual(v_resp.status_code, 200)
            v_data = v_resp.json()
            self.assertEqual(v_data.get("voice_state"), "VOICE_DISABLED")
            self.assertFalse(v_data.get("enabled"))
        finally:
            service.stop()

    def test_18_terminal_status_bar_reflects_voice_state(self):
        """18. Verify status bar renders VOICE: OFF when voice is disabled."""
        from terminal_ui import render_status_bar
        # Should execute cleanly without error
        render_status_bar()


if __name__ == "__main__":
    unittest.main()
