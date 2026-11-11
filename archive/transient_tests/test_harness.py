"""
test_harness.py
Plan-execute-verify loop and compact tool results (harness.py, agent.py hop loop):
1. tool_outcome() classifies the real result strings from tools.py (ok / error / blocked / denied).
2. compact() keeps head, key error line and tail; ResultStore/read_result return the full text by handle.
3. CallTracker flags repeated calls and repeated errors.
4. The hop loop: a tool-free final round at the hop cap (with a deterministic summary if the model still
   asks for tools), dead ends end the loop early, approval blocks do not trigger the "fix it" note,
   and long results reach the model compacted with a read_result handle.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent as agent_mod
import tools
from agents import get_registry
from harness import CallTracker, ResultStore, compact, tool_outcome

ADMIN = {"name": "Mateen Sir", "role": "admin"}
PY_ERROR = ('Errors:\nTraceback (most recent call last):\n  File "x.py", line 3, in <module>\n    print(y)\n'
            "NameError: name 'y' is not defined\nExit code: 1")


class TestOutcome(unittest.TestCase):

    def test_classification(self):
        cases = {
            "Output:\nhello": ("ok", ""),
            "Output:\nDeprecationWarning: old api\ndone": ("ok", ""),
            PY_ERROR: ("error", "NameError"),
            "Errors:\n'foo' is not recognized as a command\nExit code: 1": ("error", "nonzero_exit"),
            "Error: File 'a.py' does not exist in workspace.": ("error", "not_found"),
            "Execution timed out (exceeded 15s limit).": ("error", "timeout"),
            "Security Authorization Failed: Denied: no": ("blocked", "approval_denied"),
            "Tool 'send_email' is outside E.D.I.T.H.'s permissions (Code engineer).": ("denied", "agent_permission"),
        }
        for text, (status, kind) in cases.items():
            o = tool_outcome(text)
            self.assertEqual((o.status, o.error_kind), (status, kind), text)
        self.assertEqual(tool_outcome(PY_ERROR).key_line, "NameError: name 'y' is not defined")
        self.assertEqual(tool_outcome(PY_ERROR).exit_code, 1)
        self.assertIn("not recognized", tool_outcome("Errors:\n'foo' is not recognized\nExit code: 1").key_line)
        self.assertFalse(tool_outcome("Security Authorization Failed: Denied").fixable)

    def test_compact_keeps_error_line(self):
        big = "start\n" + "noise line\n" * 300 + "ValueError: bad value\n" + "more noise\n" * 300 + "the end"
        out, shortened = compact(big, 700, "ValueError: bad value")
        self.assertTrue(shortened)
        self.assertLess(len(out), 900)
        self.assertTrue(out.startswith("start"))
        self.assertIn("ValueError: bad value", out)
        self.assertTrue(out.endswith("the end"))
        self.assertEqual(compact("short", 700), ("short", False))

    def test_compact_keeps_salient_lines_of_ok_output(self):
        # A successful read hides nothing important: a 3B model rarely asks for the omitted middle.
        log = [f"10:00:{i:02d} INFO request {i} served" for i in range(120)]
        log[40] = "10:00:40 ERROR database connection refused on port 5433"
        out, shortened = compact("\n".join(log), 1000)
        self.assertTrue(shortened)
        self.assertIn("ERROR database connection refused", out)
        self.assertIn("error/warning lines from that part", out)
        quiet, _ = compact("\n".join(f"INFO {i}" for i in range(400)), 700)
        self.assertIn("no error/warning lines in that part", quiet)

    def test_result_store(self):
        store = ResultStore(capacity=2)
        rid = store.put("read_workspace_file", "a" * 3000)
        page = store.read(rid, 0, 1000)
        self.assertIn("chars 0-1000 of 3000", page)
        self.assertIn(f"read_result(id='{rid}', start=1000)", page)
        self.assertIn("End of result", store.read(rid.lower(), 2500, 1000))
        store.put("x", "b")
        store.put("y", "c")
        self.assertTrue(store.read(rid).startswith("Error: no stored result"))

    def test_tracker(self):
        t = CallTracker()
        ok = tool_outcome("Output:\nfine")
        self.assertEqual(t.record("list_workspace_files", {}, "a", ok), [])
        self.assertTrue(t.record("list_workspace_files", {}, "a", ok))
        self.assertFalse(t.stuck())
        t.record("list_workspace_files", {}, "a", ok)
        self.assertTrue(t.stuck())
        t2 = CallTracker()
        err = tool_outcome(PY_ERROR)
        t2.record("run_python_script", {"filename": "x.py"}, PY_ERROR + "1", err)
        warnings = t2.record("run_python_script", {"filename": "x.py", "v": 2}, PY_ERROR + "2", err)
        self.assertTrue(any("same error happened twice" in w for w in warnings))


def tool_call(name, **args):
    return json.dumps({"tool": name, "args": args})


class TestHopLoop(unittest.TestCase):

    def setUp(self):
        get_registry().pin(None)
        self.patches = [
            patch("face_id.get_active_user", return_value=ADMIN),
            patch.object(agent_mod.router, "resolve_model", side_effect=lambda m: "zaine-fast-3b"),
            patch.object(agent_mod.router, "get_instant_acknowledgment", return_value=None),
            patch("memory.reflect_on_task_async"),
            patch("ollama_profiler.log_ollama_call"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        get_registry().pin(None)

    def make_agent(self):
        a = agent_mod.ZaineAgent.__new__(agent_mod.ZaineAgent)
        a.memory = MagicMock()
        a.memory.get_persistent_context.return_value = ""
        a.memory.get_messages.return_value = [{"role": "user", "content": "task"}]
        a.ultron_mode = False
        a.last_turn_calls = []
        a._turn_event_cb = None
        a._delegation_depth = 0
        import threading
        a._chat_lock = threading.Lock()
        return a

    def run_turn(self, a, replies, message="@edith fix the script"):
        prompts = []

        def post(url, json=None, stream=False, timeout=None, **kw):
            prompts.append([dict(m) for m in json["messages"]])
            content = replies.pop(0) if replies else "done"
            r = MagicMock()
            r.raise_for_status.return_value = None
            r.iter_lines.return_value = [
                agent_mod.json.dumps({"message": {"content": content}}).encode(),
                agent_mod.json.dumps({"done": True, "eval_count": 5, "eval_duration": 1e8}).encode(),
            ]
            return r
        with patch.object(agent_mod.requests, "post", side_effect=post):
            reply = "".join(a._chat_stream_impl(message))
        return reply, prompts

    def test_final_round_at_hop_cap(self):
        a = self.make_agent()
        calls = [tool_call("list_workspace_files", subfolder=f"d{i}") for i in range(8)]
        fake = {"list_workspace_files": lambda subfolder="": f"files in {subfolder}"}
        with patch.dict(tools.TOOL_REGISTRY, fake):
            reply, prompts = self.run_turn(a, calls + ["All eight folders are listed, Sir."])
        self.assertEqual(len(prompts), 9)  # 8 tool hops for E.D.I.T.H. + 1 tool-free answer round
        self.assertIn("tool budget for this request is used up", prompts[-1][-1]["content"])
        self.assertIn("All eight folders are listed", reply)

    def test_cap_summary_when_model_keeps_calling(self):
        a = self.make_agent()
        calls = [tool_call("list_workspace_files", subfolder=f"d{i}") for i in range(9)]
        fake = {"list_workspace_files": lambda subfolder="": f"files in {subfolder}"}
        with patch.dict(tools.TOOL_REGISTRY, fake):
            reply, prompts = self.run_turn(a, calls)
        self.assertEqual(len(prompts), 9)
        self.assertIn("tool-step limit", reply)
        self.assertIn("list_workspace_files: ok", reply)
        self.assertNotIn('"tool"', reply)

    def test_dead_end_stops_early(self):
        a = self.make_agent()
        same = tool_call("run_python_script", filename="x.py")
        with patch.dict(tools.TOOL_REGISTRY, {"run_python_script": lambda filename="": PY_ERROR}):
            reply, prompts = self.run_turn(a, [same, same, same, "It fails with a NameError on y, Sir."])
        self.assertEqual(len(prompts), 4)  # stuck after 3 identical calls -> final round
        self.assertIn("same error happened twice", prompts[2][-1]["content"])
        self.assertIn("Do not repeat it", prompts[2][-1]["content"])
        self.assertIn("tool budget for this request is used up", prompts[3][-1]["content"])
        self.assertIn("NameError", reply)

    def test_error_vs_blocked_notes(self):
        a = self.make_agent()
        with patch.dict(tools.TOOL_REGISTRY, {"run_python_script": lambda filename="": PY_ERROR}):
            _, prompts = self.run_turn(a, [tool_call("run_python_script", filename="x.py"), "ok"])
        fb = prompts[1][-1]["content"]
        self.assertIn("(error, exit 1, NameError)", fb)
        self.assertIn("Fix the cause", fb)

        a = self.make_agent()
        blocked = lambda path="", content="": "Security Authorization Failed: Denied: not now"
        with patch.dict(tools.TOOL_REGISTRY, {"write_workspace_file": blocked}):
            _, prompts = self.run_turn(a, [tool_call("write_workspace_file", path="a.py", content="x"), "ok"])
        fb = prompts[1][-1]["content"]
        self.assertIn("(blocked, approval_denied)", fb)
        self.assertIn("did not approve", fb)
        self.assertNotIn("Fix the cause", fb)

    def test_long_result_compacted_with_handle(self):
        a = self.make_agent()
        long_text = "HEADER\n" + "row\n" * 2000 + "FOOTER"
        with patch.dict(tools.TOOL_REGISTRY, {"read_workspace_file": lambda path="": long_text}):
            _, prompts = self.run_turn(a, [tool_call("read_workspace_file", path="big.txt"),
                                           tool_call("read_result", id="R1", start=7), "ok"])
        first = prompts[1][-1]["content"]
        self.assertLess(len(first), 2600)  # file reads get 3x the default 700-char budget
        self.assertIn("HEADER", first)
        self.assertIn("FOOTER", first)
        self.assertIn('"read_result", "args": {"id": "R1"', first)
        second = prompts[2][-1]["content"]
        self.assertIn("[R1 from read_workspace_file: chars 7-", second)
        self.assertNotIn("shortened", second)


if __name__ == "__main__":
    unittest.main()
