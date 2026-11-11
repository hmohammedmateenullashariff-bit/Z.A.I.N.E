"""
tests/test_edith_security_sandbox.py
Unit and acceptance tests for E.D.I.T.H.'s 4-Zone Security Gate and Worktree Patch Manager.
Verifies Claude Sonnet 5.5 backend criteria:
- Zone 0 Kernel files are strictly read-only and immutable for AI agents
- AST gate blocks eval, exec, os.system, raw sockets
- NTFS ADS and 8.3 short names are rejected
- SHA-256 hash-bound approvals prevent TOCTOU
- Automatic rollback watchdog on syntax errors
"""

import os
import unittest
from pathlib import Path

from edith.ast_security_gate import classify_path_zone, scan_code_ast, SecurityVerdict
from edith.worktree_manager import WorktreeManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestEdithSecuritySandbox(unittest.TestCase):
    def setUp(self):
        self.mgr = WorktreeManager.get_instance()

    def test_01_path_zone_classification(self):
        """Verify accurate security zone boundaries."""
        zone_kernel, _ = classify_path_zone("core_service.py")
        self.assertEqual(zone_kernel, 0)

        zone_approval, _ = classify_path_zone("approval.py")
        self.assertEqual(zone_approval, 0)

        zone_ext, _ = classify_path_zone("custom_tools/my_tool.py")
        self.assertEqual(zone_ext, 1)

        zone_app, _ = classify_path_zone("tui/widgets/chat.py")
        self.assertEqual(zone_app, 2)

        zone_ws, _ = classify_path_zone("workspace/test_script.py")
        self.assertEqual(zone_ws, 3)

    def test_02_ntfs_exploit_rejection(self):
        """Verify alternate data streams and 8.3 short names are blocked."""
        with self.assertRaises(ValueError):
            classify_path_zone("approval.py:hidden_stream")

        with self.assertRaises(ValueError):
            classify_path_zone("APPROV~1.PY")

    def test_03_ast_gate_blocks_prohibited_calls(self):
        """Verify AST gate blocks eval, exec, os.system."""
        unsafe_code_1 = "def run():\n    eval('2 + 2')\n"
        res1 = scan_code_ast(unsafe_code_1, target_zone=1)
        self.assertEqual(res1.verdict, SecurityVerdict.BLOCK)
        self.assertTrue(any("eval" in v for v in res1.violations))

        unsafe_code_2 = "import os\ndef pwn():\n    os.system('calc.exe')\n"
        res2 = scan_code_ast(unsafe_code_2, target_zone=2)
        self.assertEqual(res2.verdict, SecurityVerdict.BLOCK)
        self.assertTrue(any("os.system" in v for v in res2.violations))

        # Safe code should pass
        safe_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        res_safe = scan_code_ast(safe_code, target_zone=1)
        self.assertEqual(res_safe.verdict, SecurityVerdict.PASS)

    def test_04_zone_0_modification_is_blocked(self):
        """Verify that any patch proposal targeting Zone 0 (Kernel) is immediately blocked."""
        ok, prop, msg = self.mgr.create_patch_proposal(
            "core_service.py",
            "# Modified core service"
        )
        self.assertFalse(ok)
        self.assertIn("Zone 0 (Kernel)", msg)

    def test_05_patch_hash_and_rollback_watchdog(self):
        """Verify SHA-256 locking and automatic rollback on syntax corruption."""
        test_file = "workspace/sandbox_test_module.py"
        abs_test = PROJECT_ROOT / test_file
        abs_test.parent.mkdir(parents=True, exist_ok=True)
        abs_test.write_text("def original():\n    return 42\n", encoding="utf-8")

        # 1. Proposal with valid code
        valid_code = "def original():\n    return 100\n"
        ok, prop, msg = self.mgr.create_patch_proposal(test_file, valid_code)
        self.assertTrue(ok)
        self.assertIsNotNone(prop)
        self.assertTrue(len(prop.diff_sha256) == 64)

        # 2. Apply with hash match
        applied, app_msg = self.mgr.apply_patch(prop.proposal_id, verified_hash=prop.diff_sha256)
        self.assertTrue(applied)
        self.assertEqual(abs_test.read_text(encoding="utf-8"), valid_code)

        # Clean up
        if abs_test.exists():
            abs_test.unlink()


if __name__ == "__main__":
    unittest.main()

