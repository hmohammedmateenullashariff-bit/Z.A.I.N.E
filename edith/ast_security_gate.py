"""
edith/ast_security_gate.py
Deterministic AST Security Gate and Path Zoning Engine for Project-Z (Z.A.I.N.E).
Enforces:
- 4-Zone path boundaries (Zone 0 Kernel is completely read-only for agents)
- Static Python AST inspection blocking dangerous primitives (eval, exec, raw sockets, secret exfiltration)
- Windows NTFS path normalization rejecting junctions, ADS streams, and 8.3 short names
"""

import ast
import enum
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Tuple

logger = logging.getLogger("zaine.edith.security_gate")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Zone 0: Kernel (Strictly Read-Only for ALL agents, human edit only)
ZONE_0_KERNEL_FILES = {
    "approval.py",
    "coordinator.py",
    "core_service.py",
    "core/circuit_breaker.py",
    "core/task_envelope.py",
    "edith/ast_security_gate.py",
    ".env",
    ".env.example",
    ".zaine_core.json",
    "requirements.txt",
    "run_demo.bat",
    "run_demo_fast.bat",
    "run_zaine.bat",
    "scripts/ensure_core.py"
}

# Zone 1: Extensions
ZONE_1_EXTENSION_PREFIXES = ("custom_tools", "agents", "tool_clusters.py")

# Disallowed function names and module calls in agent-generated patches
DISALLOWED_CALLS = {
    "eval",
    "exec",
    "__import__",
    "compile"
}

DISALLOWED_ATTR_CALLS = {
    ("os", "system"),
    ("os", "popen"),
    ("os", "spawn"),
    ("os", "spawnp"),
    ("os", "spawnl"),
    ("os", "spawnle"),
    ("os", "spawnlp"),
    ("os", "spawnlpe"),
    ("os", "spawnv"),
    ("os", "spawnve"),
    ("os", "spawnvp"),
    ("os", "spawnvpe"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),
    ("socket", "socket")
}


class SecurityVerdict(str, enum.Enum):
    PASS = "PASS"
    FLAG = "FLAG"
    BLOCK = "BLOCK"


@dataclass
class SecurityCheckResult:
    verdict: SecurityVerdict
    zone: int
    target_path: str
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_allowed(self) -> bool:
        return self.verdict == SecurityVerdict.PASS


def classify_path_zone(path_str: str) -> Tuple[int, str]:
    """
    Normalizes a path and classifies it into one of 4 security zones:
    Zone 0: Kernel (Locked down)
    Zone 1: Extensions (Plugins & Profiles)
    Zone 2: Application (Core Agents & TUI)
    Zone 3: Workspace (User sandbox)
    Returns: (zone: int, normalized_rel_path: str)
    """
    # 1. Reject Windows NTFS anomalies
    raw = str(path_str).strip()
    if ":" in raw and not (len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha()):
        # Alternate Data Stream attack (e.g. file.py:stream)
        raise ValueError(f"Security Alert: Alternate Data Stream detected in path '{path_str}'")

    if "~" in raw:
        # 8.3 short name bypass attempt (e.g. APPROV~1.PY)
        raise ValueError(f"Security Alert: 8.3 short name notation prohibited: '{path_str}'")

    if raw.startswith(r"\\?\\"):
        raise ValueError(f"Security Alert: Extended-length device path prohibited: '{path_str}'")

    if raw.endswith(".") or raw.endswith(" "):
        raise ValueError(f"Security Alert: Trailing dot/space path prohibited: '{path_str}'")

    # 2. Path normalization
    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        else:
            candidate = candidate.resolve()
        rel_path = candidate.relative_to(PROJECT_ROOT).as_posix().lower()
    except Exception as e:
        raise ValueError(f"Path outside project root: {path_str} ({e})")

    # 3. Classify zone
    # Zone 3: Workspace
    if rel_path.startswith("workspace/") or rel_path.startswith("demo_workspace/"):
        return 3, rel_path

    # Zone 0: Kernel
    for kf in ZONE_0_KERNEL_FILES:
        if rel_path == kf.lower() or rel_path.endswith("/" + kf.lower()):
            return 0, rel_path

    # Zone 1: Extensions
    for ext in ZONE_1_EXTENSION_PREFIXES:
        if rel_path.startswith(ext.lower()):
            return 1, rel_path

    # Zone 2: Application
    return 2, rel_path


def scan_code_ast(code: str, target_zone: int = 1, file_path: str = "") -> SecurityCheckResult:
    """
    Statically analyzes Python code using the standard AST library to detect security violations.
    """
    violations = []
    warnings = []

    # Zone 0 is immutable for agents
    if target_zone == 0:
        return SecurityCheckResult(
            verdict=SecurityVerdict.BLOCK,
            zone=0,
            target_path=file_path,
            violations=["Zone 0 (Kernel) files are strictly read-only and cannot be modified by any AI agent."]
        )

    try:
        tree = ast.parse(code, filename=file_path or "<patch>")
    except SyntaxError as e:
        return SecurityCheckResult(
            verdict=SecurityVerdict.BLOCK,
            zone=target_zone,
            target_path=file_path,
            violations=[f"SyntaxError in proposed code: {e}"]
        )

    # Walk AST nodes
    for node in ast.walk(tree):
        # 1. Direct function call checks
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in DISALLOWED_CALLS:
                    violations.append(f"Prohibited call: direct use of '{func.id}()' is forbidden in Zone {target_zone}.")
            elif isinstance(func, ast.Attribute):
                # Attribute call (e.g. os.system, subprocess.call)
                if isinstance(func.value, ast.Name):
                    caller = (func.value.id, func.attr)
                    if caller in DISALLOWED_ATTR_CALLS:
                        violations.append(
                            f"Prohibited API: '{func.value.id}.{func.attr}()' is forbidden in Zone {target_zone}."
                        )

        # 2. Secret exfiltration check in string literals
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            if any(secret in val.lower() for secret in ["x-zaine-token", "openai_api_key", "anthropic_api_key", "telegram_bot_token"]):
                warnings.append(f"Hardcoded credential/token reference detected in string: '{val[:30]}...'")

    verdict = SecurityVerdict.BLOCK if violations else (SecurityVerdict.FLAG if warnings else SecurityVerdict.PASS)
    return SecurityCheckResult(
        verdict=verdict,
        zone=target_zone,
        target_path=file_path,
        violations=violations,
        warnings=warnings
    )

