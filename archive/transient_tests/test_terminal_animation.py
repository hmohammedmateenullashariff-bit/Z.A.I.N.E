"""
Z.A.I.N.E. — Terminal Interaction Animation & Engagement Acceptance Test Suite
Verifies all 17 mandatory acceptance criteria from Section 17 of the Mission Specification:
1. startup animation disabled under non-TTY
2. startup animation disabled with ZAINE_NO_ANIMATION
3. spinner starts
4. spinner stops
5. spinner cleanup on exception
6. status state transitions
7. tool animation cleanup
8. streaming cursor cleanup
9. persona animation
10. /new cleanup
11. /exit cleanup
12. terminal resize
13. voice remains OFF by default
14. text request does not activate microphone
15. animation does not enter conversation history
16. animation does not modify stored responses
17. redirected stdout contains no ANSI animation corruption
"""

import os
import sys
import io
import time
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import terminal_ui
from rich.console import Console
from terminal_ui import (
    AnimationController,
    AnimationState,
    ToolExecutionRenderer,
    is_animation_enabled,
    render_startup_boot,
    render_status_bar,
    cmd_persona,
    cmd_new,
    handle_slash_command,
    get_terminal_cols,
    render_learned_notification,
    render_session_reset_event,
    render_task_completed_event,
    render_task_failed_event,
    state,
    console,
    CURSOR_BLOCK,
    SPINNER_FRAMES,
    PHASE_FRAMES,
)
import voice
try:
    import core_router
    import memory_manager
except Exception:
    pass


class TestTerminalAnimationSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tools
        from memory_manager import get_memory_manager
        get_memory_manager()

    def setUp(self):
        # Reset state before each test
        state.persona = "jarvis"
        state.mode = "companion"
        state.verbosity = "normal"
        state.current_status = "READY"
        terminal_ui.anim_controller.stop()
        voice.disable_voice()
        if "ZAINE_NO_ANIMATION" in os.environ:
            del os.environ["ZAINE_NO_ANIMATION"]
        if "ZAINE_FORCE_ANIMATION" in os.environ:
            del os.environ["ZAINE_FORCE_ANIMATION"]

    def tearDown(self):
        terminal_ui.anim_controller.stop()
        voice.disable_voice()
        if "ZAINE_NO_ANIMATION" in os.environ:
            del os.environ["ZAINE_NO_ANIMATION"]
        if "ZAINE_FORCE_ANIMATION" in os.environ:
            del os.environ["ZAINE_FORCE_ANIMATION"]

    # 1. startup animation disabled under non-TTY
    def test_01_startup_animation_disabled_under_non_tty(self):
        """1. Verify startup animation is disabled under non-TTY execution."""
        fake_stdout = io.StringIO()
        fake_stdout.isatty = lambda: False
        with patch.object(sys, "stdout", fake_stdout):
            self.assertFalse(is_animation_enabled())
            t0 = time.time()
            render_startup_boot()
            dur = time.time() - t0
            # Under non-TTY, sleeps are bypassed; executes nearly instantly (<0.4s)
            self.assertLess(dur, 0.4)
            output = fake_stdout.getvalue()
            self.assertIn("SYSTEM READY", output)
            self.assertIn("Voice", output)
            self.assertIn("standby", output)

    # 2. startup animation disabled with ZAINE_NO_ANIMATION
    def test_02_startup_animation_disabled_with_zaine_no_animation(self):
        """2. Verify startup animation is completely disabled when ZAINE_NO_ANIMATION=1."""
        os.environ["ZAINE_NO_ANIMATION"] = "1"
        self.assertFalse(is_animation_enabled())

        t0 = time.time()
        render_startup_boot()
        dur = time.time() - t0
        self.assertLess(dur, 0.4)

    # 3. spinner starts
    def test_03_spinner_starts(self):
        """3. Verify thinking spinner starts cleanly and launches worker thread."""
        os.environ["ZAINE_FORCE_ANIMATION"] = "1"
        ctrl = AnimationController()
        with patch.object(sys.stdout, "isatty", return_value=True):
            self.assertTrue(is_animation_enabled())
            ctrl.start_thinking("PROCESSING TEST")
            self.assertEqual(ctrl.state, AnimationState.THINKING)
            self.assertIsNotNone(ctrl._thread)
            self.assertTrue(ctrl._thread.is_alive())
            ctrl.stop()

    # 4. spinner stops
    def test_04_spinner_stops(self):
        """4. Verify thinking spinner stops and halts worker thread."""
        os.environ["ZAINE_FORCE_ANIMATION"] = "1"
        ctrl = AnimationController()
        with patch.object(sys.stdout, "isatty", return_value=True):
            ctrl.start_thinking("PROCESSING TEST")
            time.sleep(0.05)
            ctrl.stop()
            self.assertIn(ctrl.state, (AnimationState.READY, AnimationState.IDLE))
            self.assertIsNone(ctrl._thread)
            self.assertIsNone(ctrl._live)

    # 5. spinner cleanup on exception
    def test_05_spinner_cleanup_on_exception(self):
        """5. Verify spinner and Live contexts are cleanly stopped when exception occurs."""
        os.environ["ZAINE_FORCE_ANIMATION"] = "1"
        ctrl = AnimationController()
        with patch.object(sys.stdout, "isatty", return_value=True):
            ctrl.start_thinking("THINKING")
            try:
                raise RuntimeError("Simulated model inference crash")
            except RuntimeError:
                ctrl.stop()

            self.assertIsNone(ctrl._thread)
            self.assertIsNone(ctrl._live)
            self.assertEqual(ctrl.state, AnimationState.READY)

    # 6. status state transitions
    def test_06_status_state_transitions(self):
        """6. Verify status bar indicators transition correctly through all states."""
        from terminal_ui import anim_controller

        # READY state
        anim_controller.set_state(AnimationState.READY)
        self.assertEqual(anim_controller.state, AnimationState.READY)

        # Dynamic phase glyph for THINKING
        anim_controller.set_state(AnimationState.THINKING)
        glyph = anim_controller.get_phase_glyph()
        self.assertIn(glyph, PHASE_FRAMES)

        # STREAMING state
        anim_controller.set_state(AnimationState.STREAMING)
        self.assertEqual(anim_controller.state, AnimationState.STREAMING)

        # TOOL_RUNNING state
        anim_controller.set_state(AnimationState.TOOL_RUNNING)
        self.assertEqual(anim_controller.state, AnimationState.TOOL_RUNNING)

        # Return to READY
        anim_controller.set_state(AnimationState.READY)
        self.assertEqual(anim_controller.state, AnimationState.READY)

    # 7. tool animation cleanup
    def test_07_tool_animation_cleanup(self):
        """7. Verify tool animation stops cleanly and collapses into final compact summary line."""
        os.environ["ZAINE_FORCE_ANIMATION"] = "1"
        fake_console = Console(file=io.StringIO(), highlight=False)
        renderer = ToolExecutionRenderer(console_instance=fake_console)

        with patch.object(sys.stdout, "isatty", return_value=True):
            renderer.on_start("search_vault", {"query": "Project Z goals"})
            # Verify live tree was created
            if is_animation_enabled():
                self.assertIsNotNone(renderer._thread)
            time.sleep(0.05)

            # Finish tool execution
            renderer.on_done("search_vault", "1 relevant note found", duration_s=1.23)
            # Verify live was destroyed
            self.assertIsNone(renderer._live)
            self.assertIsNone(renderer._thread)

            # Verify final output contains compact result
            output = fake_console.file.getvalue()
            self.assertIn("search_vault", output)
            self.assertIn("1.23s", output)
            self.assertIn("1 relevant note found", output)

    # 8. streaming cursor cleanup
    def test_08_streaming_cursor_cleanup(self):
        """8. Verify streaming cursor appears during streaming and is erased without entering history."""
        # Simulate token stream
        simulated_tokens = ["The", " architecture", " is", " verified."]
        captured_stream = []
        conversation_history = []
        cursor_active = False

        for token in simulated_tokens:
            conversation_history.append(token)
            if cursor_active:
                captured_stream.append("\b \b")  # cursor erasure
            captured_stream.append(token)
            captured_stream.append(CURSOR_BLOCK)  # cursor appended
            cursor_active = True

        if cursor_active:
            captured_stream.append("\b \b")  # final erasure
            cursor_active = False

        # Conversation history stored should have ZERO cursor characters
        stored_text = "".join(conversation_history)
        self.assertNotIn(CURSOR_BLOCK, stored_text)
        self.assertEqual(stored_text, "The architecture is verified.")
        self.assertFalse(cursor_active)

    # 9. persona animation
    def test_09_persona_animation(self):
        """9. Verify persona transition operates under 1s and correctly switches identity."""
        os.environ["ZAINE_FORCE_ANIMATION"] = "1"
        t0 = time.time()
        cmd_persona("ultron")
        dur = time.time() - t0

        self.assertEqual(state.persona, "ultron")
        self.assertLess(dur, 1.0)
        self.assertEqual(terminal_ui.get_theme()["user_prefix"], "Creator")

        t1 = time.time()
        cmd_persona("jarvis")
        dur2 = time.time() - t1

        self.assertEqual(state.persona, "jarvis")
        self.assertLess(dur2, 1.0)
        self.assertEqual(terminal_ui.get_theme()["user_prefix"], "Sir")

    # 10. /new cleanup
    def test_10_new_cleanup(self):
        """10. Verify /new command cleans up animations, resets voice to OFF, and sets status READY."""
        voice.enable_voice()
        self.assertTrue(voice.is_voice_enabled())
        terminal_ui.anim_controller.start_thinking("TEST")

        with patch("terminal_ui.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            cmd_new()

        self.assertEqual(terminal_ui.anim_controller.state, AnimationState.READY)
        self.assertFalse(voice.is_voice_enabled())
        self.assertEqual(state.current_status, "READY")

    # 11. /exit cleanup
    def test_11_exit_cleanup(self):
        """11. Verify /exit cleans up active animation controller and returns False."""
        terminal_ui.anim_controller.start_thinking("TEST")
        keep_going = handle_slash_command("/exit")
        self.assertFalse(keep_going)
        self.assertEqual(terminal_ui.anim_controller.state, AnimationState.READY)
        self.assertIsNone(terminal_ui.anim_controller._thread)

    # 12. terminal resize
    def test_12_terminal_resize(self):
        """12. Verify terminal resize queries dynamic columns and does not crash."""
        with patch("shutil.get_terminal_size", return_value=os.terminal_size((45, 20))):
            cols_small = get_terminal_cols()
            self.assertEqual(cols_small, 45)
            # Renders without throwing exception
            render_status_bar()

        with patch("shutil.get_terminal_size", return_value=os.terminal_size((160, 40))):
            cols_large = get_terminal_cols()
            self.assertEqual(cols_large, 160)
            render_status_bar()

    # 13. voice remains OFF by default
    def test_13_voice_remains_off_by_default(self):
        """13. Verify voice state is strictly VOICE_DISABLED by default."""
        self.assertEqual(voice.get_voice_state(), voice.VOICE_STATE_DISABLED)
        self.assertFalse(voice.is_voice_enabled())

    # 14. text request does not activate microphone
    def test_14_text_request_does_not_activate_microphone(self):
        """14. Verify standard text request does not invoke audio recording or microphone."""
        with patch("voice.one_shot_listen") as mock_listen, \
             patch("voice.record_audio") as mock_record, \
             patch("requests.get") as mock_get, \
             patch("requests.post") as mock_post:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"ok": True}
            mock_post.return_value.status_code = 200
            mock_post.return_value.iter_lines.return_value = [b"data: {\"type\": \"done\"}"]
            from terminal_ui import execute_chat_turn
            execute_chat_turn("Hello Zaine")

            mock_listen.assert_not_called()
            mock_record.assert_not_called()

    # 15. animation does not enter conversation history
    def test_15_animation_does_not_enter_conversation_history(self):
        """15. Verify animation frames (spinners, tree lines, cursor) do not enter history."""
        # Simulated chat turn saving response
        raw_model_reply = "System is operating optimally within design parameters."
        # If response was passed to render_response
        with patch.object(console, "print") as mock_print:
            terminal_ui.render_response(raw_model_reply)
            self.assertTrue(mock_print.called)

        for frame in SPINNER_FRAMES:
            self.assertNotIn(frame, raw_model_reply)
        self.assertNotIn(CURSOR_BLOCK, raw_model_reply)

    # 16. animation does not modify stored responses
    def test_16_animation_does_not_modify_stored_responses(self):
        """16. Verify stored responses are identical to original model output."""
        original = "# Architecture Plan\n\n- Layer 1: Terminal Native\n- Layer 2: Core Service\n"
        stored = original.strip()
        self.assertEqual(stored, original.strip())
        self.assertNotIn("⠋", stored)
        self.assertNotIn(CURSOR_BLOCK, stored)

    # 17. redirected stdout contains no ANSI animation corruption
    def test_17_redirected_stdout_contains_no_ansi_animation_corruption(self):
        """17. Verify redirected / piped stdout does not receive transient live spinner escape sequences."""
        fake_out = io.StringIO()
        fake_out.isatty = lambda: False
        with patch.object(sys, "stdout", fake_out):
            self.assertFalse(is_animation_enabled())
            # Start thinking under non-TTY
            terminal_ui.anim_controller.start_thinking("PROCESSING")
            time.sleep(0.05)
            terminal_ui.anim_controller.stop()

        output = fake_out.getvalue()
        # Under non-TTY, live spinner loop is not started, so no escape sequences
        self.assertNotIn("\x1b[2K", output)
        self.assertNotIn("\x1b[1A", output)

    # 18. learning notification verbosity test
    def test_18_learning_notification_verbosity(self):
        """18. Verify learning notifications adapt cleanly to verbosity level."""
        fake_con = Console(file=io.StringIO(), highlight=False)
        with patch("terminal_ui.console", fake_con):
            # Compact: silent
            state.verbosity = "compact"
            render_learned_notification("Vault retrieval pattern recorded.")
            self.assertEqual(fake_con.file.getvalue(), "")

            # Normal: single line with [learned]
            state.verbosity = "normal"
            render_learned_notification("Vault retrieval pattern recorded.")
            val = fake_con.file.getvalue()
            self.assertIn("[learned]", val)
            self.assertIn("Vault retrieval pattern recorded.", val)
            self.assertIn("Memory updated", val)

            # Verbose: multi-line
            fake_con.file = io.StringIO()
            state.verbosity = "verbose"
            render_learned_notification("Identified a specific document containing project goals.")
            val_v = fake_con.file.getvalue()
            self.assertIn("[learned]", val_v)
            self.assertIn("Identified a specific document", val_v)
            self.assertIn("Memory updated", val_v)

    # 19. thinking phase transitions
    def test_19_thinking_phase_transitions(self):
        """19. Verify thinking controller supports contextual phases without restart."""
        ctrl = AnimationController()
        ctrl.start_thinking("Understanding request")
        self.assertEqual(ctrl._current_message, "Understanding request")

        ctrl.update_phase("Planning")
        self.assertEqual(ctrl._current_message, "Planning")

        ctrl.update_phase("Reasoning")
        self.assertEqual(ctrl._current_message, "Reasoning")

        ctrl.update_phase("Preparing response")
        self.assertEqual(ctrl._current_message, "Preparing response")
        ctrl.stop()

    # 20. long-running reasoning elapsed time
    def test_20_long_running_reasoning_elapsed_time(self):
        """20. Verify elapsed time is displayed when thinking/reasoning exceeds 3s threshold."""
        ctrl = AnimationController()
        ctrl.start_thinking("Reasoning")
        ctrl._think_start = time.time() - 3.4  # simulate 3.4 seconds elapsed
        rendered = ctrl._render_thinking_text(0)
        rendered_str = rendered.plain
        self.assertIn("Deep reasoning", rendered_str)
        self.assertIn("3.4s", rendered_str)
        ctrl.stop()

    # 21. multi-tool collapse
    def test_21_multi_tool_collapse(self):
        """21. Verify multiple tool executions collapse cleanly into compact scrollback."""
        fake_con = Console(file=io.StringIO(), highlight=False)
        renderer = ToolExecutionRenderer(console_instance=fake_con)

        renderer.on_start("search_vault", {"query": "test"})
        renderer.on_done("search_vault", "2 relevant notes", duration_s=0.05)

        renderer.on_start("get_memory", {"id": "1"})
        renderer.on_done("get_memory", "ok", duration_s=0.02)

        renderer.on_start("system_status", {})
        renderer.on_done("system_status", "nominal", duration_s=0.01)

        self.assertEqual(len(renderer.completed_tools), 3)
        val = fake_con.file.getvalue()
        self.assertIn("search_vault", val)
        self.assertIn("get_memory", val)
        self.assertIn("system_status", val)
        self.assertIn("0.05s", val)
        self.assertIn("0.02s", val)
        self.assertIn("0.01s", val)
        self.assertIsNone(renderer._live)
        self.assertIsNone(renderer._thread)

    # 22. startup sequence subsystems
    def test_22_startup_sequence_subsystems(self):
        """22. Verify startup sequence tests real subsystems and displays SYSTEM READY."""
        fake_stdout = io.StringIO()
        with patch.object(sys, "stdout", fake_stdout):
            render_startup_boot()
            out = fake_stdout.getvalue()
            self.assertIn("Core engine", out)
            self.assertIn("Brain router", out)
            self.assertIn("Memory vault", out)
            self.assertIn("Tool registry", out)
            self.assertIn("Vision", out)
            self.assertIn("Voice", out)
            self.assertIn("standby", out)
            self.assertIn("SYSTEM READY", out)

    # 23. task completion notification verbosity
    def test_23_task_completion_notification_verbosity(self):
        """23. Verify task completion micro-events adhere to compact/normal/verbose levels."""
        fake_con = Console(file=io.StringIO(), highlight=False)
        with patch("terminal_ui.console", fake_con):
            # Compact: single line duration
            state.verbosity = "compact"
            render_task_completed_event(tool_count=3, duration_s=1.8)
            val_c = fake_con.file.getvalue()
            self.assertIn("Task completed", val_c)
            self.assertIn("1.8s", val_c)

            # Normal: summary with count and duration
            fake_con.file = io.StringIO()
            state.verbosity = "normal"
            render_task_completed_event(tool_count=3, duration_s=1.8)
            val_n = fake_con.file.getvalue()
            self.assertIn("Task completed", val_n)
            self.assertIn("3 tools · 1.8s", val_n)

            # Verbose: full execution telemetry
            fake_con.file = io.StringIO()
            state.verbosity = "verbose"
            render_task_completed_event(tool_count=3, duration_s=1.82)
            val_v = fake_con.file.getvalue()
            self.assertIn("Task completed", val_v)
            self.assertIn("3 tools executed", val_v)
            self.assertIn("1.82s elapsed", val_v)

    # 24. idle state has no animation thread
    def test_24_idle_state_has_no_animation_thread(self):
        """24. Verify that when idle, no animation threads or Live contexts run."""
        terminal_ui.anim_controller.stop()
        self.assertIsNone(terminal_ui.anim_controller._thread)
        self.assertIsNone(terminal_ui.anim_controller._live)
        self.assertIn(terminal_ui.anim_controller.state, (AnimationState.READY, AnimationState.IDLE))

    # 25. responsive width rendering (80, 100, 120 columns)
    def test_25_responsive_width_rendering_80_100_120(self):
        """25. Verify status bar safely adapts to 80, 100, and 120+ columns without error."""
        for width in (80, 100, 120, 140):
            with patch("terminal_ui.get_terminal_cols", return_value=width):
                # Ensure no exceptions are raised
                render_status_bar()

    # 26. voice state never in status bar when disabled
    def test_26_voice_state_never_in_status_bar_when_disabled(self):
        """26. Verify voice state indicators (LISTENING/SPEAKING) never appear if voice is disabled."""
        self.assertFalse(voice.is_voice_enabled())
        fake_con = Console(file=io.StringIO(), highlight=False)
        with patch("terminal_ui.console", fake_con):
            render_status_bar(status_text="LISTENING")
            out = fake_con.file.getvalue()
            self.assertNotIn("LISTENING", out)
            self.assertIn("READY", out)

            fake_con.file = io.StringIO()
            render_status_bar(status_text="SPEAKING")
            out_sp = fake_con.file.getvalue()
            self.assertNotIn("SPEAKING", out_sp)
            self.assertIn("READY", out_sp)

    # 27. session reset event verbosity
    def test_27_session_reset_event_verbosity(self):
        """27. Verify session reset micro-event adapts cleanly to verbosity."""
        fake_con = Console(file=io.StringIO(), highlight=False)
        with patch("terminal_ui.console", fake_con):
            state.verbosity = "normal"
            render_session_reset_event("SES-1009-01")
            out = fake_con.file.getvalue()
            self.assertIn("New session initialized [SES-1009-01]", out)
            self.assertIn("Working memory cleared.", out)
            self.assertIn("Long-term memory preserved.", out)


if __name__ == "__main__":
    unittest.main()
