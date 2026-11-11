"""
tests/test_sessions.py
Unit tests verifying session-based chat history and thread persistence.
"""

import time
import unittest
from db.sessions import session_manager


class TestSessionManager(unittest.TestCase):
    def test_01_create_and_list_session(self):
        sid = session_manager.create_session(title="Quantum Mechanics Review", agent_id="friday")
        time.sleep(0.3)  # Allow async writer thread to flush
        sessions = session_manager.list_sessions()
        found = any(s["id"] == sid for s in sessions)
        self.assertTrue(found, "Newly created session must be present in session list")

    def test_02_append_and_retrieve_messages(self):
        sid = session_manager.create_session(title="Debugging Session", agent_id="edith")
        session_manager.append_message(sid, "user", "Why did the breaker trip?", "qwen2.5:3b")
        session_manager.append_message(sid, "assistant", "Cooldown duration was 30s.", "qwen2.5:3b")
        time.sleep(0.3)

        messages = session_manager.get_messages(sid)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Why did the breaker trip?")
        self.assertEqual(messages[1]["role"], "assistant")

    def test_03_delete_session(self):
        sid = session_manager.create_session(title="Temporary Session")
        session_manager.append_message(sid, "user", "Temp message")
        time.sleep(0.3)
        session_manager.delete_session(sid)
        time.sleep(0.3)

        sessions = session_manager.list_sessions()
        self.assertFalse(any(s["id"] == sid for s in sessions))
        messages = session_manager.get_messages(sid)
        self.assertEqual(len(messages), 0)


if __name__ == "__main__":
    unittest.main()

