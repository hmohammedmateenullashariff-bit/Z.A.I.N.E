"""
edith/
E.D.I.T.H. Autonomous Code Engineering and Self-Modification Security Sandbox.
Implements Claude Sonnet 5.5 backend criteria:
- 4-Zone Security Model (Zone 0 Kernel lockdown, Zone 1 Extensions, Zone 2 App, Zone 3 Workspace)
- Deterministic AST Security Gate blocking prohibited execution primitives
- Isolated Git Worktree management for patch generation
- SHA-256 hash-bound human approval closing Time-of-Check to Time-of-Use (TOCTOU) exploits
"""

from edith.ast_security_gate import (
    classify_path_zone,
    scan_code_ast,
    SecurityVerdict,
    SecurityCheckResult
)
from edith.worktree_manager import (
    WorktreeManager,
    CodePatchProposal,
    get_worktree_manager
)

__all__ = [
    "classify_path_zone",
    "scan_code_ast",
    "SecurityVerdict",
    "SecurityCheckResult",
    "WorktreeManager",
    "CodePatchProposal",
    "get_worktree_manager"
]

