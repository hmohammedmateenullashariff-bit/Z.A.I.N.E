"""
test_stage5_digraph.py
Execution digraph model, renderer and system-topology builder (all offline):
1. Hop attribution: tools belong to the LLM call that requested them; a new hop starts only when
   the model speaks again after tools ran.
2. Approval outcomes come from the tool result (approved / denied / expired).
3. abort() leaves nothing running and records the reason.
4. Layered rendering draws boxes, arrows and every node; empty and narrow canvases are handled.
5. The system graph degrades to an honest offline view when core and Ollama are unreachable.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tui.exec_graph import ExecGraph, classify_tool_result, RUNNING, WAITING
from tui.widgets.digraph import render_digraph, render_trace
import tui.system_graph as sg


def ev(stage, tool="", data=None):
    return {"type": "tool_event", "stage": stage, "tool": tool, "data": data}


def two_hop_turn(result="3 passed"):
    g = ExecGraph()
    g.start_turn("write prime.py and run tests")
    for e in [
        ev("route", "router", {"tier": "REFLEX", "model": "zaine-fast-3b"}),
        ev("profiler", "m", {"model": "zaine-fast-3b", "eval_count": 96, "eval_duration_s": 2.0}),
        ev("start", "write_workspace_file", {"filepath": "prime.py"}),
        ev("done", "write_workspace_file", "Wrote prime.py"),
        ev("start", "execute_command", {"command": "pytest -q"}),
        ev("approval_required", "execute_command", {"proposal_id": "ACT-1", "command": "pytest -q"}),
    ]:
        g.apply(e)
    return g


class TestExecGraph(unittest.TestCase):

    def test_01_tools_attach_to_requesting_hop(self):
        g = two_hop_turn()
        models = [n for n in g.nodes.values() if n.kind == "model"]
        self.assertEqual(len(models), 1)
        for nid, n in g.nodes.items():
            if n.kind == "tool":
                self.assertIn((models[0].node_id, nid), g.edges)
        g.apply(ev("done", "execute_command", "3 passed"))
        g.apply({"type": "token", "content": "All good"})
        g.apply(ev("profiler", "m", {"model": "zaine-fast-3b", "eval_count": 40, "eval_duration_s": 1.0}))
        g.apply({"type": "done", "reply": "All good"})
        s = g.summary()
        self.assertEqual(s["hops"], 2)
        self.assertEqual(s["tokens"], 136)
        self.assertEqual(s["tools"], 2)
        self.assertFalse(s["active"])
        hop2 = [n for n in g.nodes.values() if n.kind == "model"][1]
        sources = {src for src, dst in g.edges if dst == hop2.node_id}
        self.assertEqual({g.nodes[s_].kind for s_ in sources}, {"tool"})
        self.assertEqual(len(sources), 2)

    def test_02_approval_outcomes_from_tool_result(self):
        for result, outcome, tool_status in [
            ("3 passed", "APPROVED", "ok"),
            ("Security Authorization Failed: Denied: no", "DENIED", "blocked"),
            ("Security Authorization Failed: Expired: no decision on ACT-1 within 180s.", "EXPIRED", "blocked"),
        ]:
            g = two_hop_turn()
            appr = next(n for n in g.nodes.values() if n.kind == "approval")
            self.assertEqual(appr.status, WAITING)
            g.apply(ev("done", "execute_command", result))
            self.assertEqual(appr.meta["outcome"], outcome)
            tool = next(n for n in g.nodes.values() if n.kind == "tool" and n.label == "execute_command")
            self.assertEqual(tool.status, tool_status)
            self.assertEqual(g.summary()["approvals"], [("ACT-1", outcome)])

    def test_03_classify_tool_result(self):
        self.assertEqual(classify_tool_result("Error: file not found")[0], "failed")
        self.assertEqual(classify_tool_result("ok")[0], "ok")
        self.assertEqual(classify_tool_result(None)[0], "ok")

    def test_04_abort_settles_everything(self):
        g = two_hop_turn()
        g.abort("Idle gap timeout (20s)")
        self.assertFalse(g.is_active)
        self.assertFalse(any(n.status in (RUNNING, WAITING) for n in g.nodes.values()))
        last = list(g.nodes.values())[-1]
        self.assertEqual(last.kind, "error")
        self.assertIn("Idle gap", last.detail)
        g.abort("again")  # idempotent once ended
        self.assertEqual(sum(1 for n in g.nodes.values() if n.kind == "error"), 1)

    def test_05_layers_are_topological(self):
        g = two_hop_turn()
        layers = g.layers()
        depth = {nid: i for i, col in enumerate(layers) for nid in col}
        for src, dst in g.edges:
            self.assertLess(depth[src], depth[dst])


class TestRenderer(unittest.TestCase):

    def test_01_box_render_contains_all_nodes_and_arrows(self):
        g = two_hop_turn()
        g.apply(ev("done", "execute_command", "3 passed"))
        g.apply({"type": "done", "reply": "done"})
        text = render_digraph(g, 200, 14).plain
        for label in ("Operator prompt", "Router · REFLEX", "LLM hop 1", "write_workspace_file",
                      "execute_command", "Guardrail approval", "Reply"):
            self.assertIn(label, text)
        self.assertIn("▶", text)
        self.assertIn("╭─ TOOL", text)
        self.assertEqual(len(text.splitlines()), 14)

    def test_02_narrow_canvas_marks_hidden_columns(self):
        text = render_digraph(two_hop_turn(), 60, 10).plain
        self.assertIn("◀+", text)

    def test_03_empty_graph_shows_hint(self):
        self.assertIn("nothing here", render_digraph(ExecGraph(), 80, 10, empty_hint="nothing here").plain)

    def test_04_trace_lists_steps(self):
        trace = render_trace(two_hop_turn(), 40).plain
        self.assertIn("ROUTER", trace)
        self.assertIn("GUARD", trace)
        self.assertIn("n/a", render_trace(None, 40).plain)


class TestSystemGraph(unittest.TestCase):

    def test_01_offline_core_and_ollama(self):
        with patch.object(sg, "_get_json", return_value=None), patch.object(sg, "_port_open", return_value=False):
            g = sg.collect_system_graph("http://127.0.0.1:7860")
        self.assertEqual(g.nodes["core"].status, "offline")
        self.assertEqual(g.nodes["router"].status, "offline")
        self.assertEqual(g.nodes["telegram"].status, "offline")
        self.assertFalse(g.facts["core_up"])
        self.assertIn("cluster:SYSTEM", g.nodes)  # real clusters still listed
        text = render_digraph(g, 160, 30, style="pill").plain
        self.assertIn("Core Service", text)
        self.assertIn("unreachable", text)

    def test_02_loaded_model_marked(self):
        def fake(url, timeout=0.8):
            if url.endswith("/api/status"):
                return {"port": 7860, "model_loaded": True, "warming": False, "active_model": "zaine-fast-3b", "mode": "jarvis"}
            if url.endswith("/api/tags"):
                return {"models": [{"name": "zaine-fast-3b:latest", "size": 2 * 1024 ** 3},
                                   {"name": "nomic-embed-text:latest", "size": 1}]}
            if url.endswith("/api/ps"):
                return {"models": [{"name": "zaine-fast-3b:latest", "size_vram": int(2.2 * 1024 ** 3)}]}
            if url.endswith("/api/approvals"):
                return {"ok": True, "pending": [{"id": "ACT-1"}]}
            return None
        with patch.object(sg, "_get_json", side_effect=fake), patch.object(sg, "_port_open", return_value=True):
            g = sg.collect_system_graph("http://127.0.0.1:7860")
        node = g.nodes["model:zaine-fast-3b"]
        self.assertEqual(node.status, "loaded")
        self.assertIn("VRAM", node.detail)
        self.assertIn("★", node.detail)
        self.assertNotIn("model:nomic-embed-text", g.nodes)
        self.assertEqual(g.facts["pending_approvals"], 1)
        self.assertEqual(g.nodes["guard"].status, "waiting")
        self.assertTrue(g.facts["telegram_online"])


if __name__ == "__main__":
    unittest.main()
