"""
tests/test_prompt_compiler.py
Unit tests verifying the Prefix-Cache-Aware Prompt Compiler.
Ensures static prefix byte-level immutability across turns for 100% KV-cache hits.
"""

import unittest
from core.prompt_compiler import prompt_compiler


class TestPromptCompiler(unittest.TestCase):
    def test_01_static_prefix_immutability(self):
        # Two turns with different history and clock context must share the exact same static prefix
        compiled_1 = prompt_compiler.compile(
            agent_id="jarvis",
            agent_name="J.A.R.V.I.S.",
            clearance="STANDARD",
            history=[{"role": "user", "content": "Turn 1 request"}],
            dynamic_context={"timestamp_iso": "2026-11-08T22:00:00Z"},
            learned_rules=["Rule A"],
        )

        compiled_2 = prompt_compiler.compile(
            agent_id="jarvis",
            agent_name="J.A.R.V.I.S.",
            clearance="STANDARD",
            history=[
                {"role": "user", "content": "Turn 1 request"},
                {"role": "assistant", "content": "Turn 1 answer"},
                {"role": "user", "content": "Turn 2 request"},
            ],
            dynamic_context={"timestamp_iso": "2026-11-08T22:05:00Z"},
            learned_rules=["Rule A", "Rule B"],
        )

        # Slot 0 must be 100% byte-identical
        self.assertEqual(compiled_1.messages[0], compiled_2.messages[0])
        self.assertEqual(compiled_1.static_hash, compiled_2.static_hash)
        self.assertGreater(compiled_1.cached_prefix_tokens, 50)

    def test_02_dynamic_tail_segregation(self):
        compiled = prompt_compiler.compile(
            agent_id="friday",
            agent_name="F.R.I.D.A.Y.",
            clearance="TACTICAL",
            history=[{"role": "user", "content": "Scan airspace"}],
            learned_rules=["Avoid blocked sectors"],
        )
        # Message count: Slot 0 (system static), Slot 1 (system dynamic meta), Slot 2 (user turn)
        self.assertEqual(len(compiled.messages), 3)
        self.assertEqual(compiled.messages[0]["role"], "system")
        self.assertIn("F.R.I.D.A.Y.", compiled.messages[0]["content"])
        self.assertIn("ACTIVE LEARNED RULES", compiled.messages[1]["content"])
        self.assertEqual(compiled.messages[2]["content"], "Scan airspace")


if __name__ == "__main__":
    unittest.main()

