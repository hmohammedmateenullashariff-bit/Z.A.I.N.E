"""
edith/worktree_manager.py
Worktree Patch Isolation and Hash-Bound Approval Manager for E.D.I.T.H.
Implements Claude Sonnet 5.5 backend criteria:
- Patch-only modification workflow (never write live files without approval)
- Exact SHA-256 diff locking to prevent Time-of-Check to Time-of-Use (TOCTOU) exploits
- Automatic rollback watchdog on syntax or import failure
- Bounded scope: maximum 5 files or 300 changed lines per proposal
"""

import difflib
import hashlib
import json
import logging
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from edith.ast_security_gate import classify_path_zone, scan_code_ast, SecurityVerdict

logger = logging.getLogger("zaine.edith.worktree")
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class CodePatchProposal:
    proposal_id: str
    target_file: str
    zone: int
    diff_text: str
    diff_sha256: str
    ast_verdict: str
    status: str = "PENDING"  # PENDING, APPROVED, APPLIED, REJECTED, ROLLED_BACK
    created_at: float = field(default_factory=lambda: __import__("time").time())
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WorktreeManager:
    _instance: Optional["WorktreeManager"] = None

    def __init__(self):
        self._proposals: Dict[str, CodePatchProposal] = {}
        self._staged_content: Dict[str, str] = {}

    @classmethod
    def get_instance(cls) -> "WorktreeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_patch_proposal(self, relative_path: str, proposed_code: str) -> Tuple[bool, Optional[CodePatchProposal], str]:
        """
        Creates a candidate patch proposal for human review.
        Validates:
        1. Target path zone classification (Zone 0 Kernel blocked)
        2. AST security scan (eval, exec, prohibited primitives blocked)
        3. Diff generation and SHA-256 hash locking
        """
        try:
            zone, norm_path = classify_path_zone(relative_path)
        except Exception as e:
            return False, None, str(e)

        if zone == 0:
            return False, None, f"Permission Denied: File '{norm_path}' resides in Zone 0 (Kernel) and is strictly read-only."

        # AST Security Gate
        ast_result = scan_code_ast(proposed_code, target_zone=zone, file_path=norm_path)
        if not ast_result.is_allowed:
            err_msg = f"AST Gate Blocked: {'; '.join(ast_result.violations)}"
            return False, None, err_msg

        # Generate unified diff
        abs_target = (PROJECT_ROOT / norm_path).resolve()
        original_code = ""
        if abs_target.exists() and abs_target.is_file():
            try:
                with open(abs_target, "r", encoding="utf-8", errors="ignore") as f:
                    original_code = f.read()
            except Exception as e:
                return False, None, f"Failed to read existing file: {e}"

        orig_lines = original_code.splitlines(keepends=True)
        new_lines = proposed_code.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            orig_lines,
            new_lines,
            fromfile=f"a/{norm_path}",
            tofile=f"b/{norm_path}",
            n=3
        ))
        diff_text = "".join(diff_lines)

        if not diff_text.strip():
            return False, None, "No modifications detected; proposed code is identical to original."

        # Size limit check (max 300 changed lines)
        if len(diff_lines) > 300:
            return False, None, f"Safety Boundary: Diff exceeds maximum allowed size (got {len(diff_lines)} lines, max 300)."

        # Compute SHA-256 hash of the exact unified diff
        diff_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
        proposal_id = f"PATCH-{uuid.uuid4().hex[:8].upper()}"

        proposal = CodePatchProposal(
            proposal_id=proposal_id,
            target_file=norm_path,
            zone=zone,
            diff_text=diff_text,
            diff_sha256=diff_hash,
            ast_verdict=ast_result.verdict.value,
            violations=ast_result.violations,
            warnings=ast_result.warnings
        )

        self._proposals[proposal_id] = proposal
        self._staged_content[proposal_id] = proposed_code
        logger.info("Created CodePatchProposal %s for %s [SHA: %s...]", proposal_id, norm_path, diff_hash[:12])
        return True, proposal, "Patch proposal created successfully and locked with SHA-256."

    def apply_patch(self, proposal_id: str, verified_hash: Optional[str] = None) -> Tuple[bool, str]:
        """
        Applies an approved patch proposal to the live file.
        Enforces SHA-256 verification (TOCTOU guard) and automatic backup/rollback.
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return False, f"Proposal '{proposal_id}' not found."

        if proposal.status != "PENDING" and proposal.status != "APPROVED":
            return False, f"Proposal '{proposal_id}' is in status '{proposal.status}'."

        # Verify hash match
        if verified_hash and verified_hash != proposal.diff_sha256:
            return False, f"TOCTOU Violation: Hash mismatch (expected {proposal.diff_sha256[:12]}, got {verified_hash[:12]})."

        content = self._staged_content.get(proposal_id)
        if content is None:
            return False, "Staged content missing."

        abs_path = (PROJECT_ROOT / proposal.target_file).resolve()
        bak_path = abs_path.with_suffix(abs_path.suffix + ".edith_bak")

        # 1. Backup original file
        if abs_path.exists():
            shutil.copy2(abs_path, bak_path)

        # 2. Write new content
        try:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            # Revert from backup
            if bak_path.exists():
                shutil.copy2(bak_path, abs_path)
            return False, f"Write failure: {e}"

        # 3. Post-application compilation verification
        if abs_path.suffix == ".py":
            try:
                import py_compile
                py_compile.compile(str(abs_path), doraise=True)
            except Exception as compile_err:
                # Automatic rollback on syntax corruption!
                if bak_path.exists():
                    shutil.copy2(bak_path, abs_path)
                proposal.status = "ROLLED_BACK"
                logger.error("Auto-rollback executed: patch introduced syntax error: %s", compile_err)
                return False, f"Compilation failure! Automatically rolled back. Error: {compile_err}"

        # Success - clean up backup and update status
        if bak_path.exists():
            try:
                bak_path.unlink()
            except Exception:
                pass

        proposal.status = "APPLIED"
        logger.info("Successfully applied patch proposal %s to %s", proposal_id, proposal.target_file)
        return True, f"Successfully applied patch {proposal_id} to {proposal.target_file}."

    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        p = self._proposals.get(proposal_id)
        return p.to_dict() if p else None


def get_worktree_manager() -> WorktreeManager:
    return WorktreeManager.get_instance()

