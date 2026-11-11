"""
test_subagents.py
VisionQuest sub-agents (agents/profiles.json, agents/registry.py, agent.py):
1. Profiles load and validate (unique ids, known clusters and tools).
2. Selection order: @mention > /agent pin > cluster routing > default; mixed requests stay with J.A.R.V.I.S.
3. Prompts carry the agent role and only its tools; the ULTRON critic gets no tool section.
4. Tool permissions are enforced at execution.
5. ask_agent delegation: consulted agent runs with its own prompt/permissions; refusals for depth,
   self-delegation, unknown/background agents and parallel calls.
6. The execution graph shows AGENT nodes and delegation branches; /agent works in the TUI.
"""

import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent as agent_mod
from agents import get_registry, select_agent, parse_mention
from tool_clusters import build_clustered_system_prompt
from tui.exec_graph import ExecGraph

ADMIN = {"name": "Mateen Sir", "role": "admin"}


class TestRegistry(unittest.TestCase):

    def tearDown(self):
        get_registry().pin(None)

    def test_profiles_load(self):
        reg = get_registry()
        names = {p.display_name for p in reg.profiles.values()}
        self.assertTrue({"J.A.R.V.I.S.", "E.D.I.T.H.", "F.R.I.D.A.Y.", "VISION", "ULTRON", "D.U.M.-E & U"} <= names)
        self.assertEqual(reg.default.agent_id, "zaine-jarvis")
        self.assertTrue(reg.default.allows("any_runtime_custom_tool"))
        edith = reg.profiles["zaine-edith"]
        self.assertTrue(edith.allows("write_workspace_file"))
        self.assertTrue(edith.allows("ask_agent"))
        self.assertFalse(edith.allows("send_email"))
        self.assertEqual(len(reg.profiles["zaine-ultron"].allowed_tools), 0)

    def test_selection_order(self):
        reg = get_registry()
        self.assertEqual(select_agent("hello").profile.agent_id, "zaine-jarvis")
        self.assertEqual(select_agent("write a python function to sort a list").profile.agent_id, "zaine-edith")
        self.assertEqual(select_agent("how much ram is free").profile.agent_id, "zaine-friday")
        self.assertEqual(select_agent("what do you remember about my projects").profile.agent_id, "zaine-vision")
        mixed = select_agent("open chrome and write code")
        self.assertEqual(mixed.profile.agent_id, "zaine-jarvis")
        self.assertIn("mixed", mixed.reason)
        # ULTRON is never auto-routed, only addressed
        self.assertNotEqual(select_agent("critique this").profile.agent_id, "zaine-ultron")
        m = select_agent("@ultron review: delete all logs")
        self.assertEqual((m.profile.agent_id, m.source, m.message), ("zaine-ultron", "mention", "review: delete all logs"))
        ok, _ = reg.pin("friday")
        self.assertTrue(ok)
        self.assertEqual(select_agent("write code").profile.agent_id, "zaine-friday")
        self.assertEqual(select_agent("@edith write code").profile.agent_id, "zaine-edith")  # mention beats pin
        self.assertTrue(reg.pin("auto")[0])
        self.assertIsNone(reg.pinned)
        self.assertFalse(reg.pin("dume")[0])
        self.assertFalse(reg.pin("nobody")[0])

    def test_mention_parsing(self):
        self.assertEqual(parse_mention("@nobody hi")[0], None)
        self.assertEqual(parse_mention("email me @edith later")[0], None)
        p, rest = parse_mention("@E.D.I.T.H., fix it")
        self.assertEqual((p.agent_id, rest), ("zaine-edith", "fix it"))


class TestPromptsAndEnforcement(unittest.TestCase):

    def test_prompt_shaping(self):
        reg = get_registry()
        vision = build_clustered_system_prompt("", active_clusters=["VAULT_MEMORY"], active_user=ADMIN,
                                               agent_profile=reg.profiles["zaine-vision"])
        self.assertIn("ACTIVE AGENT: VISION", vision)
        self.assertIn("- search_web(", vision)                # extra tool from another cluster
        self.assertIn("AGENT COLLABORATION", vision)
        self.assertNotIn('"tool": "open_application"', vision)  # no examples for tools it cannot use
        ultron = build_clustered_system_prompt("", active_clusters=[], active_user=ADMIN,
                                               agent_profile=reg.profiles["zaine-ultron"])
        self.assertIn("NO tools", ultron)
        self.assertNotIn("ACTIVE SPECIALIZED TOOLS", ultron)
        nested = build_clustered_system_prompt("", active_clusters=["DEV_CODE"], active_user=ADMIN,
                                               agent_profile=reg.profiles["zaine-edith"], allow_delegation=False)
        self.assertNotIn("AGENT COLLABORATION", nested)

    def test_execution_enforcement(self):
        a = agent_mod.ZaineAgent.__new__(agent_mod.ZaineAgent)
        a.active_agent = get_registry().profiles["zaine-edith"]
        with patch("face_id.get_active_user", return_value=ADMIN):
            out = a._execute_tool({"tool": "send_email", "args": {"to": "x@y.z", "subject": "s", "body": "b"}})
            self.assertIn("outside E.D.I.T.H.'s permissions", out)
            self.assertIn("Local:", a._execute_tool({"tool": "get_datetime", "args": {}}))


class TestDelegation(unittest.TestCase):

    def make_agent(self, active="zaine-edith"):
        a = agent_mod.ZaineAgent.__new__(agent_mod.ZaineAgent)
        a.memory = MagicMock()
        a.memory.get_persistent_context.return_value = ""
        a.ultron_mode = False
        a.last_turn_calls = []
        a.active_agent = get_registry().profiles[active]
        a._turn_model = "zaine-fast-3b"
        a._turn_thread = threading.current_thread()
        a._delegation_depth = 0
        a.events = []
        a._turn_event_cb = lambda s, t, d: a.events.append((s, t, d))
        return a

    @staticmethod
    def fake_ollama(replies):
        prompts = []

        def post(url, json=None, timeout=None, **kw):
            prompts.append(json["messages"])
            r = MagicMock()
            r.raise_for_status.return_value = None
            r.json.return_value = {"message": {"content": replies.pop(0)}, "eval_count": 10, "eval_duration": 5e8}
            return r
        return post, prompts

    def test_consult_ultron(self):
        a = self.make_agent()
        post, prompts = self.fake_ollama(["Bug: n < 2 returns True."])
        with patch.object(agent_mod.requests, "post", side_effect=post), patch("face_id.get_active_user", return_value=ADMIN):
            out = a._execute_tool({"tool": "ask_agent", "args": {"agent": "ultron", "request": "review is_prime"}})
        self.assertTrue(out.startswith("ULTRON replied:"))
        self.assertIn("n < 2", out)
        self.assertEqual(a.active_agent.agent_id, "zaine-edith")
        self.assertEqual(a._delegation_depth, 0)
        self.assertIn("NO tools", prompts[0][0]["content"])
        self.assertIn("consulted by E.D.I.T.H.", prompts[0][0]["content"])
        self.assertEqual([e[0] for e in a.events], ["delegate_start", "profiler", "delegate_done"])

    def test_consulted_agent_uses_its_own_permissions(self):
        a = self.make_agent(active="zaine-jarvis")
        post, _ = self.fake_ollama(['{"tool": "send_email", "args": {"to": "x@y.z", "subject": "s", "body": "b"}}',
                                    "I cannot send email in my role."])
        with patch.object(agent_mod.requests, "post", side_effect=post), patch("face_id.get_active_user", return_value=ADMIN):
            out = a._execute_tool({"tool": "ask_agent", "args": {"agent": "edith", "request": "email the report"}})
        done = [d for s, t, d in a.events if s == "done"]
        self.assertIn("outside E.D.I.T.H.'s permissions", done[0])
        self.assertIn("cannot send email", out)
        self.assertEqual(a.active_agent.agent_id, "zaine-jarvis")

    def test_refusals(self):
        a = self.make_agent()
        with patch("face_id.get_active_user", return_value=ADMIN):
            self.assertIn("cannot consult itself", a._execute_tool({"tool": "ask_agent", "args": {"agent": "edith", "request": "x"}}))
            self.assertIn("unknown agent", a._execute_tool({"tool": "delegate", "args": {"to": "nobody", "task": "x"}}))
            self.assertIn("background agent", a._execute_tool({"tool": "ask_agent", "args": {"agent": "dume", "request": "x"}}))
            self.assertIn("needs 'agent'", a._execute_tool({"tool": "ask_agent", "args": {"agent": "ultron"}}))
            a._delegation_depth = 1
            self.assertIn("cannot delegate further", a._execute_tool({"tool": "ask_agent", "args": {"agent": "vision", "request": "x"}}))
            a._delegation_depth = 0
            result = {}
            t = threading.Thread(target=lambda: result.update(
                r=a._execute_tool({"tool": "ask_agent", "args": {"agent": "vision", "request": "x"}})))
            t.start()
            t.join()
            self.assertIn("on its own", result["r"])
            a.active_agent = get_registry().profiles["zaine-ultron"]
            self.assertIn("outside ULTRON's permissions", a._execute_tool({"tool": "ask_agent", "args": {"agent": "edith", "request": "x"}}))


class TestGraphAndTUI(unittest.IsolatedAsyncioTestCase):

    def test_graph_agent_and_delegation_nodes(self):
        def ev(stage, tool="", data=None):
            return {"type": "tool_event", "stage": stage, "tool": tool, "data": data}
        g = ExecGraph()
        g.start_turn("write is_prime and get it reviewed")
        for e in [
            ev("route", "router", {"tier": "REFLEX", "model": "m"}),
            ev("agent", "zaine-edith", {"display_name": "E.D.I.T.H.", "reason": "routed"}),
            ev("profiler", "m", {"eval_count": 10, "eval_duration_s": 1.0}),
            ev("start", "ask_agent", {"agent": "ultron", "request": "review"}),
            ev("delegate_start", "zaine-ultron", {"from_display": "E.D.I.T.H.", "to_display": "ULTRON", "request": "review"}),
            ev("profiler", "m", {"eval_count": 5, "eval_duration_s": 1.0}),
            ev("delegate_done", "zaine-ultron", {"to_display": "ULTRON", "ok": True, "answer": "ok"}),
            ev("done", "ask_agent", "ULTRON replied: ok"),
            ev("profiler", "m", {"eval_count": 7, "eval_duration_s": 1.0}),
            {"type": "done", "reply": "Done."},
        ]:
            g.apply(e)
        labels = [n.label for n in g.nodes.values()]
        self.assertEqual(labels, ["Operator prompt", "Router · REFLEX", "E.D.I.T.H.", "E.D.I.T.H. hop 1", "ask_agent",
                                  "ULTRON", "ULTRON hop 1", "E.D.I.T.H. hop 2", "Reply"])
        by_label = {n.label: nid for nid, n in g.nodes.items()}
        self.assertIn((by_label["ask_agent"], by_label["ULTRON"]), g.edges)
        self.assertIn((by_label["ULTRON hop 1"], by_label["E.D.I.T.H. hop 2"]), g.edges)
        self.assertEqual(g.summary()["agent"], "E.D.I.T.H.")
        self.assertEqual(g.summary()["delegations"], [("ULTRON", "ok")])

    async def test_agent_command_lists_and_pins(self):
        from tui.app import ZaineTUI
        from tui.widgets import ChatLog, AssistantTurnCard, HeaderBar
        listing = {"ok": True, "pinned": None, "last": None,
                   "agents": [p.summary() for p in get_registry().profiles.values()]}

        async def fake_get(base_url=None):
            return listing

        async def fake_set(name, base_url=None):
            return {"ok": True, "pinned": "zaine-edith", "display_name": "E.D.I.T.H.", "message": "E.D.I.T.H. pinned"}

        app = ZaineTUI()
        with patch("tui.app.get_agents", side_effect=fake_get), patch("tui.app.set_agent", side_effect=fake_set):
            async with app.run_test(size=(160, 45)) as pilot:
                app._dispatch_user_turn("/agent")
                await pilot.pause(0.3)
                table = list(app.query_one(ChatLog).query(AssistantTurnCard))[-1].markdown_text
                self.assertIn("VisionQuest Agents", table)
                self.assertIn("E.D.I.T.H.", table)
                self.assertIn("`@edith`", table)
                app._dispatch_user_turn("/agent edith")
                await pilot.pause(0.3)
                header = app.query_one(HeaderBar)
                self.assertTrue(header.agent_pinned)
                self.assertIn("E.D.I.T.H.", header.render().plain)


if __name__ == "__main__":
    unittest.main()
