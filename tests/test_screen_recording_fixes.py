"""
tests/test_screen_recording_fixes.py
Comprehensive regression tests for issues identified in Screen Recording 2026-11-04 164133:
1. System Graph auth header inclusion (fixing 'CORE OFFLINE' / 'NO MODEL' false negative)
2. Obsidian Memory Modal button layout and text visibility
3. Timeout safety (gap timeout expanded to 60s, heartbeat resets liveness)
4. Pseudo-tool parsing recovery ([TOOL] "trigger_youtube_pipeline", {"args": []})
5. delete_workspace_files tool implementation
6. Router classification for YouTube pipeline & complex media tasks to DEEP_CODE (zaine-coder-7b)
"""

import unittest
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestScreenRecordingFixes(unittest.TestCase):

    def test_01_system_graph_auth_header(self):
        """Verifies _get_json includes X-Zaine-Token from get_auth_headers."""
        from tui import system_graph
        import inspect
        src = inspect.getsource(system_graph._get_json)
        self.assertIn("get_auth_headers", src)
        self.assertIn("headers.update", src)

    def test_02_obsidian_modal_button_styles(self):
        """Verifies ObsidianMemoryModal buttons use border: none; height: 1 to ensure text is never clipped."""
        from tui.widgets.obsidian_modal import ObsidianMemoryModal
        css = ObsidianMemoryModal.DEFAULT_CSS
        self.assertIn("#node-buttons-row Button {", css)
        self.assertIn("border: none;", css)
        self.assertIn("height: 1;", css)

    def test_03_pseudo_tool_recovery_parsing(self):
        """Verifies agent recovers from [TOOL] 'name', {args} pseudo-tool formatting."""
        from agent import ZaineAgent
        raw_llm_hallucination = (
            'Sure, Mateen sir, Let\'s ensure all existing videos and audio files are removed to comply '
            'with the directive. [TOOL] "delete_workspace_files", {"subfolder": "videos/audio/old_videos_and_audios"} '
            'After that, we can start the YouTube pipeline for new content creation. [TOOL] "trigger_youtube_pipeline", {"args": []}'
        )
        agent = ZaineAgent.__new__(ZaineAgent)
        calls = agent._try_parse_tool_calls(raw_llm_hallucination)
        self.assertGreaterEqual(len(calls), 2)
        tool_names = [c["tool"] for c in calls]
        self.assertIn("delete_workspace_files", tool_names)
        self.assertIn("trigger_youtube_pipeline", tool_names)
        self.assertEqual(calls[0]["args"].get("subfolder"), "videos/audio/old_videos_and_audios")

    def test_04_delete_workspace_files_tool(self):
        """Verifies delete_workspace_files safely deletes workspace files and handles non-existent paths."""
        from tools import delete_workspace_files, write_workspace_file, list_workspace_files
        write_workspace_file("temp_test_cleanup/sample.txt", "dummy audio")
        res = list_workspace_files("temp_test_cleanup")
        self.assertIn("sample.txt", res)
        del_res = delete_workspace_files("temp_test_cleanup")
        self.assertIn("Successfully deleted", del_res)
        del_empty = delete_workspace_files("non_existent_folder_xyz")
        self.assertIn("does not exist", del_empty)

    def test_05_router_youtube_pipeline_tier(self):
        """Verifies YouTube pipeline prompts classify to DEEP_CODE and resolve to coder model."""
        from core_router import router
        user_prompt = "hi zaine lets start our youtube pipeline right now and start uploading new content , we will use no old videos and audios + songs from now on"
        tier = router.classify_task_tier(user_prompt)
        self.assertEqual(tier, "DEEP_CODE")
        coder_model = router.resolve_model(router.coder_model)
        self.assertTrue("coder" in coder_model.lower() or "7b" in coder_model.lower())

    def test_06_idle_gap_timeout_ceiling(self):
        """Verifies idle gap timeout is expanded from 20s to >= 60s for local LLM inference."""
        import inspect
        from tui import app
        src = inspect.getsource(app.ZaineTUI.stream_agent_response)
        self.assertIn("ZAINE_IDLE_TIMEOUT", src)
        self.assertIn("60.0", src)


if __name__ == "__main__":
    unittest.main()
