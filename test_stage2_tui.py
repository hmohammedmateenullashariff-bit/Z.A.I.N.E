"""
Z.A.I.N.E Stage 2 Headless Textual Pilot and SSE Unit Tests
Verifies:
1. SSE streaming client event parsing & timeout handling.
2. Textual TUI live streaming integration (ReasoningBlock, ToolLine, AssistantTurnCard).
3. Live throughput & TTFT metrics calculation.
4. Esc cancellation behavior.
5. Slash commands dispatching and system card generation.
"""

import sys
import time
import asyncio
import unittest
from pathlib import Path
from typing import AsyncIterator, Dict, Any
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tui.app import ZaineTUI
from tui.client import (
    stream_chat_events,
    StreamTimeoutError,
    StreamCancelledError,
    get_core_service_url,
)
from tui.widgets import (
    ChatLog,
    UserTurnCard,
    AssistantTurnCard,
    ReasoningBlock,
    ToolLine,
    SystemCard,
    AgentStateHUD,
    HeaderBar,
    FooterBar,
)


class TestStage2TUI(unittest.IsolatedAsyncioTestCase):
    """Test suite for Stage 2 TUI and SSE streaming integration."""

    async def test_01_sse_client_event_parsing(self):
        """Verify stream_chat_events parses all SSE event types."""
        sse_lines = [
            b"data: {\"type\": \"queued\", \"position\": 2}\n\n",
            b"data: {\"type\": \"running\", \"waited_seconds\": 0.12}\n\n",
            b"data: {\"type\": \"tool_event\", \"stage\": \"route\", \"tool\": \"router\", \"data\": {\"tier\": \"REFLEX\", \"model\": \"qwen2.5:3b\"}}\n\n",
            b"data: {\"type\": \"tool_event\", \"stage\": \"think\", \"tool\": \"reasoning\", \"data\": \"analyzing query\"}\n\n",
            b"data: {\"type\": \"tool_event\", \"stage\": \"think_done\", \"tool\": \"reasoning\", \"data\": \"\"}\n\n",
            b"data: {\"type\": \"tool_event\", \"stage\": \"start\", \"tool\": \"search_vault\", \"data\": \"query='zara'\"}\n\n",
            b"data: {\"type\": \"tool_event\", \"stage\": \"done\", \"tool\": \"search_vault\", \"data\": {\"status\": \"ok\"}}\n\n",
            b"data: {\"type\": \"token\", \"content\": \"Hello\"}\n\n",
            b"data: {\"type\": \"token\", \"content\": \"Sir\"}\n\n",
            b"data: {\"type\": \"done\", \"ok\": true, \"reply\": \"Hello Sir\", \"mode\": \"jarvis\"}\n\n",
        ]

        # Mock an async line iterator
        class MockResponse:
            status_code = 200
            async def aiter_lines(self):
                for line in sse_lines:
                    yield line.decode("utf-8")
            async def aread(self):
                return b""

        class MockAsyncContext:
            async def __aenter__(self):
                return MockResponse()
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        class MockClient:
            def stream(self, method, url, json=None):
                return MockAsyncContext()
            async def aclose(self):
                pass

        events = []
        async for ev in stream_chat_events(
            message="hello",
            base_url="http://127.0.0.1:7860",
            client=MockClient(),
        ):
            events.append(ev)

        self.assertEqual(len(events), 10)
        self.assertEqual(events[0]["type"], "queued")
        self.assertEqual(events[0]["position"], 2)
        self.assertEqual(events[1]["type"], "running")
        self.assertEqual(events[2]["stage"], "route")
        self.assertEqual(events[3]["stage"], "think")
        self.assertEqual(events[4]["stage"], "think_done")
        self.assertEqual(events[5]["stage"], "start")
        self.assertEqual(events[6]["stage"], "done")
        self.assertEqual(events[7]["type"], "token")
        self.assertEqual(events[7]["content"], "Hello")
        self.assertEqual(events[8]["content"], "Sir")
        self.assertEqual(events[9]["type"], "done")

    async def test_02_sse_timeout_enforcement(self):
        """Verify StreamTimeoutError is raised when chunk arrival exceeds timeout."""
        class StallingResponse:
            status_code = 200
            async def aiter_lines(self):
                yield "data: {\"type\": \"running\"}\n\n"
                await asyncio.sleep(0.5)  # Stall
                yield "data: {\"type\": \"token\", \"content\": \"slow\"}\n\n"

        class MockAsyncContext:
            async def __aenter__(self):
                return StallingResponse()
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        class MockClient:
            def stream(self, method, url, json=None):
                return MockAsyncContext()
            async def aclose(self):
                pass

        with self.assertRaises(StreamTimeoutError):
            async for _ in stream_chat_events(
                message="test timeout",
                base_url="http://127.0.0.1:7860",
                default_first_token_timeout=0.1,  # Short timeout for testing
                idle_gap_timeout=0.1,
                client=MockClient(),
            ):
                pass

    async def test_03_textual_pilot_live_streaming_turn(self):
        """Verify Textual Pilot mounts reasoning, tools, and token stream."""
        mock_events = [
            {"type": "queued", "position": 1},
            {"type": "running", "waited_seconds": 0.05},
            {"type": "tool_event", "stage": "route", "tool": "router", "data": {"tier": "REFLEX", "model": "qwen2.5:3b"}},
            {"type": "tool_event", "stage": "think", "tool": "reasoning", "data": "Evaluating query... "},
            {"type": "tool_event", "stage": "think_done", "tool": "reasoning", "data": ""},
            {"type": "tool_event", "stage": "start", "tool": "system_status", "data": "telemetry"},
            {"type": "tool_event", "stage": "done", "tool": "system_status", "data": "ok"},
            {"type": "token", "content": "All"},
            {"type": "token", "content": "systems"},
            {"type": "token", "content": "nominal."},
            {"type": "done", "ok": True, "reply": "All systems nominal.", "mode": "jarvis"},
        ]

        async def mock_stream_chat_events(*args, **kwargs):
            for ev in mock_events:
                yield ev
                await asyncio.sleep(0.01)

        app = ZaineTUI()
        with patch("tui.app.stream_chat_events", side_effect=mock_stream_chat_events):
            async with app.run_test(size=(140, 45)) as pilot:
                # Trigger stream turn
                app.stream_agent_response("check status")

                # Allow worker to run and process events
                for _ in range(15):
                    await pilot.pause(0.05)
                    if not app.is_streaming:
                        break

                chat_log = app.query_one(ChatLog)

                # Check Reasoning block was mounted and completed
                reasonings = list(chat_log.query(ReasoningBlock))
                self.assertGreaterEqual(len(reasonings), 2)
                latest_reasoning = reasonings[-1]
                self.assertIn("Evaluating query...", latest_reasoning.content)
                self.assertTrue(latest_reasoning.is_complete)

                # Check ToolLine was mounted and completed
                tools = list(chat_log.query(ToolLine))
                self.assertGreaterEqual(len(tools), 2)
                latest_tool = tools[-1]
                self.assertEqual(latest_tool.tool_name, "system_status")
                self.assertEqual(latest_tool.status, "COMPLETED")

                # Check AssistantTurnCard was mounted with tokens
                assistant_cards = list(chat_log.query(AssistantTurnCard))
                self.assertGreaterEqual(len(assistant_cards), 2)
                latest_assistant = assistant_cards[-1]
                self.assertIn("All systems nominal.", latest_assistant.markdown_text)

                # Check HUD metrics updated
                hud = app.query_one(AgentStateHUD)
                self.assertNotEqual(hud.last_ttft, "n/a")
                self.assertNotEqual(hud.last_throughput, "n/a")

    async def test_04_textual_pilot_cancellation(self):
        """Verify pressing Esc cancels live streaming cleanly."""
        async def mock_endless_stream(*args, **kwargs):
            yield {"type": "running"}
            while True:
                yield {"type": "token", "content": "token"}
                await asyncio.sleep(0.1)

        app = ZaineTUI()
        with patch("tui.app.stream_chat_events", side_effect=mock_endless_stream):
            async with app.run_test(size=(140, 45)) as pilot:
                app.stream_agent_response("endless stream")
                await pilot.pause(0.05)
                self.assertTrue(app.is_streaming)

                # Press Esc to cancel
                await pilot.press("escape")
                await pilot.pause(0.05)

                self.assertFalse(app.is_streaming)
                chat_log = app.query_one(ChatLog)
                cancelled_cards = [c for c in chat_log.query(SystemCard) if c.level == "cancelled"]
                self.assertGreaterEqual(len(cancelled_cards), 1)

    async def test_05_textual_pilot_slash_commands(self):
        """Verify slash commands dispatch to system cards and handlers."""
        app = ZaineTUI()
        async with app.run_test(size=(140, 45)) as pilot:
            inp = app.query_one("#user-input")
            chat_log = app.query_one(ChatLog)

            # 1. /help
            inp.focus()
            inp.value = "/help"
            await inp.action_submit()
            await pilot.pause(0.05)
            assistant_cards = list(chat_log.query(AssistantTurnCard))
            self.assertIn("Z.A.I.N.E Neural Command System Index", assistant_cards[-1].markdown_text)

            # 2. /models
            inp.focus()
            inp.value = "/models"
            await inp.action_submit()
            await pilot.pause(0.05)
            assistant_cards = list(chat_log.query(AssistantTurnCard))
            self.assertIn("Cognitive Neural Models & Tiers", assistant_cards[-1].markdown_text)

            # 3. /memory
            inp.focus()
            inp.value = "/memory"
            await inp.action_submit()
            await pilot.pause(0.05)
            assistant_cards = list(chat_log.query(AssistantTurnCard))
            self.assertIn("Memory Subsystem & Obsidian Vault", assistant_cards[-1].markdown_text)

            # 4. /clear
            inp.focus()
            inp.value = "/clear"
            await inp.action_submit()
            await pilot.pause(0.05)
            self.assertEqual(len(list(chat_log.query(UserTurnCard))), 0)


if __name__ == "__main__":
    unittest.main()
