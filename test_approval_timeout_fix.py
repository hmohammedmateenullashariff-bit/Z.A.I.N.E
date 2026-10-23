"""
test_approval_timeout_fix.py
Unit & Verification Tests for:
1. Client idle & first-token timeout pausing when 'approval_required' is emitted.
2. Heartbeat pings keeping SSE stream alive.
3. Clean request cancellation unblocking RequestCoordinator / CoreService to eliminate cascading deadlock.
4. In-TUI approval handling via POST /api/approval/respond.
5. ApprovalCard mounting and interactive state updates in Textual TUI.
"""

import sys
import os
import json
import time
import uuid
import socket
import asyncio
import unittest
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from coordinator import get_request_coordinator
from core_service import CoreService
from approval import ApprovalRegistry, require_approval, set_approval_listener, clear_approval_listener
from tui.client import stream_chat_events, respond_to_approval, cancel_chat_request
from tui.widgets.chat import ApprovalCard, ChatLog
from tui.app import ZaineTUI


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MockApprovalServerHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler to simulate delayed SSE responses with heartbeats."""

    def log_message(self, format, *args):
        return

    def do_POST(self):
        if self.path == "/api/chat/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            # 1. Start event
            evt1 = {"type": "tool_event", "stage": "start", "tool": "execute_command", "data": "npm install"}
            self.wfile.write(f"data: {json.dumps(evt1)}\n\n".encode("utf-8"))
            self.wfile.flush()

            # 2. Approval required event
            evt2 = {
                "type": "tool_event",
                "stage": "approval_required",
                "tool": "execute_command",
                "data": {"proposal_id": "ACT-TEST1", "command": "npm install pkg", "reason": "Package install"}
            }
            self.wfile.write(f"data: {json.dumps(evt2)}\n\n".encode("utf-8"))
            self.wfile.flush()

            # 3. Simulate human deliberation delay (1.5s, while client timeout is 0.5s)
            time.sleep(0.8)
            # Emit heartbeat comment
            self.wfile.write(b": ping\n\n")
            self.wfile.flush()
            time.sleep(0.8)

            # 4. Stream token after approval
            evt3 = {"type": "token", "content": "Command execution authorized."}
            self.wfile.write(f"data: {json.dumps(evt3)}\n\n".encode("utf-8"))
            self.wfile.flush()

            # 5. Done event
            evt4 = {"type": "done", "ok": True, "reply": "Command execution authorized."}
            self.wfile.write(f"data: {json.dumps(evt4)}\n\n".encode("utf-8"))
            self.wfile.flush()
            return


class TestApprovalTimeoutAndDeadlockFix(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Keep test proposals out of the real data/zaine_approvals.db and never send
        # approval cards to the paired Telegram account.
        import tempfile
        import approval
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._orig_db_path = approval.DB_PATH
        cls._orig_dispatch = ApprovalRegistry.__dict__["_dispatch_telegram_alert"]
        approval.DB_PATH = Path(cls._tmpdir.name) / "zaine_approvals_test.db"
        ApprovalRegistry._dispatch_telegram_alert = staticmethod(lambda *args, **kwargs: None)

    @classmethod
    def tearDownClass(cls):
        import approval
        approval.DB_PATH = cls._orig_db_path
        ApprovalRegistry._dispatch_telegram_alert = cls._orig_dispatch
        cls._tmpdir.cleanup()

    def setUp(self):
        self.coordinator = get_request_coordinator()
        self.coordinator.reset_for_testing()
        clear_approval_listener()

    def tearDown(self):
        self.coordinator.reset_for_testing()
        clear_approval_listener()

    def test_a_sse_approval_required_pauses_client_timeout(self):
        """Verifies that stage='approval_required' pauses the client timeout timer."""
        port = find_free_port()
        server = HTTPServer(("127.0.0.1", port), MockApprovalServerHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        async def _run_client():
            events = []
            # Client has strict 0.5s timeout; server waits 1.6s total!
            async for ev in stream_chat_events(
                message="install something",
                base_url=f"http://127.0.0.1:{port}",
                default_first_token_timeout=0.5,
                idle_gap_timeout=0.5,
            ):
                events.append(ev)
            return events

        try:
            received_events = asyncio.run(_run_client())
            # Check events
            types = [e.get("type") for e in received_events]
            stages = [e.get("stage") for e in received_events if e.get("type") == "tool_event"]

            self.assertIn("tool_event", types)
            self.assertIn("approval_required", stages)
            self.assertIn("token", types)
            self.assertIn("done", types)
        finally:
            server.shutdown()
            server.server_close()

    def test_b_request_cancellation_unblocks_coordinator_and_prevents_deadlock(self):
        """
        Verifies that canceling a request waiting on approval clears coordinator
        and lets the next user prompt execute immediately without deadlocking.
        """
        port = find_free_port()

        class MockHangingAgent:
            def __init__(self):
                self.chat_calls = 0

            def chat_stream(self, user_msg, on_tool_event=None):
                self.chat_calls += 1
                if "hang" in user_msg:
                    # Simulate approval proposal creation and waiting
                    pid = ApprovalRegistry.create_proposal(
                        action_type="PACKAGE_INSTALL",
                        title="Mock install",
                        description="Hanging test",
                        code_or_cmd="npm install evil",
                        tool_name="execute_command"
                    )
                    # Block on approval with 30s timeout
                    ApprovalRegistry.wait_for_decision(pid, timeout_seconds=30, poll_interval=0.2)
                    yield "Finished wait"
                else:
                    yield f"Processed prompt: {user_msg}"

            def chat(self, user_msg):
                return f"Processed prompt: {user_msg}"

        core = CoreService(agent=MockHangingAgent(), port=port)
        core.start_server()
        time.sleep(0.3)

        base_url = f"http://127.0.0.1:{port}"
        req_id_1 = f"term-hang-{uuid.uuid4().hex[:6]}"

        try:
            async def _run_deadlock_test():
                # Step 1: Start Turn 1 that hangs on approval
                agen = stream_chat_events(
                    message="please hang now",
                    base_url=base_url,
                    request_id=req_id_1,
                    default_first_token_timeout=5.0,
                )
                first_event = await anext(agen)
                if first_event.get("type") == "warming":
                    first_event = await anext(agen)
                self.assertEqual(first_event.get("type"), "running")

                # Verify coordinator is busy with req_id_1
                telem = self.coordinator.get_queue_telemetry()
                self.assertEqual(telem.get("running"), req_id_1)

                # Step 2: Client cancels Turn 1 (operator hits Esc or aborts)
                cancel_res = await cancel_chat_request(req_id_1, base_url=base_url)
                self.assertTrue(cancel_res.get("ok"))
                try:
                    await agen.aclose()
                except Exception:
                    pass

                # Step 3: Verify coordinator immediately freed the running request
                await asyncio.sleep(0.4)
                telem_after = self.coordinator.get_queue_telemetry()
                self.assertIsNone(telem_after.get("running"))

                # Step 4: Turn 2 (e.g. "is there an issue zaine ??") must process instantly
                req_id_2 = f"term-next-{uuid.uuid4().hex[:6]}"
                replies = []
                async for ev in stream_chat_events(
                    message="is there an issue zaine ??",
                    base_url=base_url,
                    request_id=req_id_2,
                    default_first_token_timeout=3.0,
                ):
                    if ev.get("type") == "token":
                        replies.append(ev.get("content"))

                self.assertTrue(len(replies) > 0)
                self.assertIn("Processed prompt: is there an issue zaine ??", "".join(replies))

            asyncio.run(_run_deadlock_test())
        finally:
            core.stop()

    def test_c_approval_respond_endpoint_approves_action(self):
        """Verifies POST /api/approval/respond directly unblocks ApprovalRegistry."""
        port = find_free_port()
        core = CoreService(port=port)
        core.start_server()
        time.sleep(0.3)
        base_url = f"http://127.0.0.1:{port}"

        prop_id = ApprovalRegistry.create_proposal(
            action_type="SHELL_EXEC",
            title="Test Shell Action",
            description="Run command",
            code_or_cmd="echo hello",
        )

        decision_result = []

        def _waiter():
            status, note = ApprovalRegistry.wait_for_decision(prop_id, timeout_seconds=5, poll_interval=0.1)
            decision_result.append((status, note))

        t = threading.Thread(target=_waiter, daemon=True)
        t.start()
        time.sleep(0.2)

        # Call POST /api/approval/respond
        resp = asyncio.run(respond_to_approval(
            proposal_id=prop_id,
            decision="approve",
            note="Approved in TUI unit test",
            base_url=base_url
        ))

        self.assertTrue(resp.get("ok"))
        self.assertEqual(resp.get("status"), "APPROVED")

        t.join(timeout=2.0)
        self.assertFalse(t.is_alive())
        self.assertEqual(decision_result[0][0], "APPROVED")

        core.stop()

    def test_d_tui_approval_card_resolution(self):
        """Verifies ApprovalCard mounts and updates state on resolution."""
        card = ApprovalCard(
            proposal_id="ACT-4242",
            command="npx skills add brag",
            reason="External package installation",
            tool_name="execute_command"
        )
        self.assertEqual(card.proposal_id, "ACT-4242")
        self.assertEqual(card.status, "PENDING")

        card.set_resolved("approve", note="Authorized")
        self.assertEqual(card.status, "APPROVED")

        expired = ApprovalCard(proposal_id="ACT-4243", command="dir", reason="r", tool_name="execute_command")
        expired.set_resolved("EXPIRED", note="No decision within 180s")
        self.assertEqual(expired.status, "EXPIRED")

    def test_e_execute_command_requires_approval_for_package_install(self):
        """Verifies execute_command intercepts package install commands and enforces approval."""
        from tools import execute_command

        cmd = "npx skills add https://github.com/latent-spaces/brag --skill brag"
        result_holder = []

        def _run_cmd():
            out = execute_command(cmd)
            result_holder.append(out)

        t = threading.Thread(target=_run_cmd, daemon=True)
        t.start()
        time.sleep(0.3)

        # Confirm proposal was created in ApprovalRegistry
        pending = ApprovalRegistry.list_pending()
        matching = [p for p in pending if "npx skills add" in p.get("title", "")]
        self.assertTrue(len(matching) > 0, "Expected pending proposal for npx package installation")

        prop_id = matching[0]["id"]
        # Deny the proposal
        ApprovalRegistry.deny(prop_id, note="Denied by operator in security test")

        t.join(timeout=2.0)
        self.assertFalse(t.is_alive())
        self.assertIn("Security Authorization Failed", result_holder[0])

    def test_f_open_application_requires_approval(self):
        """Verifies open_application creates an approval proposal and refuses to launch subprocess without approval."""
        from unittest.mock import patch
        from tools import open_application

        result_holder = []
        with patch("subprocess.Popen") as mock_popen:
            def _run_app():
                out = open_application("notepad")
                result_holder.append(out)

            t = threading.Thread(target=_run_app, daemon=True)
            t.start()
            time.sleep(0.3)

            # Confirm proposal was created in ApprovalRegistry
            pending = ApprovalRegistry.list_pending()
            matching = [p for p in pending if p.get("tool_name") == "open_application" or "notepad" in p.get("title", "").lower()]
            self.assertTrue(len(matching) > 0, "Expected pending proposal for open_application")

            prop_id = matching[0]["id"]
            # Deny the proposal
            ApprovalRegistry.deny(prop_id, note="Denied by operator in security test")

            t.join(timeout=2.0)
            self.assertFalse(t.is_alive())
            self.assertTrue(len(result_holder) > 0)
            self.assertIn("Security Authorization Failed", result_holder[0])
            # Strict verification: subprocess.Popen was NEVER called
            mock_popen.assert_not_called()

    def test_g_demo_mode_requires_approval_for_harmless_command(self):
        """In ZAINE_DEMO=1, verifies harmless commands like 'echo hi' raise a proposal and do not run until approved; denied means not run."""
        from unittest.mock import patch, MagicMock
        from tools import execute_command

        old_demo = os.environ.get("ZAINE_DEMO")
        os.environ["ZAINE_DEMO"] = "1"
        try:
            # 1. Denied path: raises proposal, does not run while pending, denied means not run
            result_holder = []
            with patch("subprocess.run") as mock_run:
                def _run_cmd():
                    out = execute_command("echo hi")
                    result_holder.append(out)

                t = threading.Thread(target=_run_cmd, daemon=True)
                t.start()
                time.sleep(0.3)

                # Must not run while pending
                mock_run.assert_not_called()

                # Confirm proposal was created in ApprovalRegistry
                pending = ApprovalRegistry.list_pending()
                matching = [p for p in pending if p.get("action_type") == "COMMAND" and "echo hi" in p.get("title", "")]
                self.assertTrue(len(matching) > 0, "Expected pending proposal with action_type COMMAND for 'echo hi'")

                prop_id = matching[0]["id"]
                ApprovalRegistry.deny(prop_id, note="Denied harmless command in test")

                t.join(timeout=2.0)
                self.assertFalse(t.is_alive())
                self.assertTrue(len(result_holder) > 0)
                self.assertIn("Security Authorization Failed", result_holder[0])
                mock_run.assert_not_called()

            # 2. Approved path: raises proposal, does not run until approved, runs when approved
            result_holder_app = []
            mock_res = MagicMock(stdout="hi\n", stderr="", returncode=0)
            with patch("subprocess.run", return_value=mock_res) as mock_run_app:
                def _run_cmd_app():
                    out = execute_command("echo hi")
                    result_holder_app.append(out)

                t2 = threading.Thread(target=_run_cmd_app, daemon=True)
                t2.start()
                time.sleep(0.3)

                # Must not run until approved
                mock_run_app.assert_not_called()

                pending2 = ApprovalRegistry.list_pending()
                matching2 = [p for p in pending2 if p.get("action_type") == "COMMAND" and "echo hi" in p.get("title", "")]
                self.assertTrue(len(matching2) > 0)

                ApprovalRegistry.approve(matching2[0]["id"], note="Approved harmless command in test")
                t2.join(timeout=2.0)
                self.assertFalse(t2.is_alive())
                mock_run_app.assert_called_once()
                self.assertEqual(result_holder_app[0], "STDOUT:\nhi")
        finally:
            if old_demo is not None:
                os.environ["ZAINE_DEMO"] = old_demo
            else:
                os.environ.pop("ZAINE_DEMO", None)

    def test_h_demo_mode_requires_approval_for_read_command(self):
        """In ZAINE_DEMO=1, verifies read commands like 'type notes.txt' raise a proposal and do not run until approved; denied means not run."""
        from unittest.mock import patch, MagicMock
        from tools import execute_command

        old_demo = os.environ.get("ZAINE_DEMO")
        os.environ["ZAINE_DEMO"] = "1"
        try:
            # 1. Denied path: raises proposal, does not run while pending, denied means not run
            result_holder = []
            with patch("subprocess.run") as mock_run:
                def _run_cmd():
                    out = execute_command("type notes.txt")
                    result_holder.append(out)

                t = threading.Thread(target=_run_cmd, daemon=True)
                t.start()
                time.sleep(0.3)

                # Must not run while pending
                mock_run.assert_not_called()

                # Confirm proposal was created in ApprovalRegistry
                pending = ApprovalRegistry.list_pending()
                matching = [p for p in pending if p.get("action_type") == "COMMAND" and "type notes.txt" in p.get("title", "")]
                self.assertTrue(len(matching) > 0, "Expected pending proposal with action_type COMMAND for 'type notes.txt'")

                prop_id = matching[0]["id"]
                ApprovalRegistry.deny(prop_id, note="Denied read command in test")

                t.join(timeout=2.0)
                self.assertFalse(t.is_alive())
                self.assertTrue(len(result_holder) > 0)
                self.assertIn("Security Authorization Failed", result_holder[0])
                mock_run.assert_not_called()

            # 2. Approved path: raises proposal, does not run until approved, runs when approved
            result_holder_app = []
            mock_res = MagicMock(stdout="meeting notes\n", stderr="", returncode=0)
            with patch("subprocess.run", return_value=mock_res) as mock_run_app:
                def _run_cmd_app():
                    out = execute_command("type notes.txt")
                    result_holder_app.append(out)

                t2 = threading.Thread(target=_run_cmd_app, daemon=True)
                t2.start()
                time.sleep(0.3)

                # Must not run until approved
                mock_run_app.assert_not_called()

                pending2 = ApprovalRegistry.list_pending()
                matching2 = [p for p in pending2 if p.get("action_type") == "COMMAND" and "type notes.txt" in p.get("title", "")]
                self.assertTrue(len(matching2) > 0)

                ApprovalRegistry.approve(matching2[0]["id"], note="Approved read command in test")
                t2.join(timeout=2.0)
                self.assertFalse(t2.is_alive())
                mock_run_app.assert_called_once()
                self.assertEqual(result_holder_app[0], "STDOUT:\nmeeting notes")
        finally:
            if old_demo is not None:
                os.environ["ZAINE_DEMO"] = old_demo
            else:
                os.environ.pop("ZAINE_DEMO", None)


if __name__ == "__main__":
    unittest.main()
