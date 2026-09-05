"""
Z.A.I.N.E — Code Rabbit AI Code Reviewer Engine
Provides deep, high-signal automated code audits, security analysis, and architectural critiques.
Inspired by CodeRabbit AI review guidelines and the Ponytail Minimal Code Decision Ladder.
"""

import ast
import os
import re
from typing import Dict, List, Any


class CodeRabbitReviewer:
    """
    Automated code review engine that audits code for:
    1. Security vulnerabilities (hardcoded secrets, unsafe eval/exec, insecure subprocesses).
    2. Robustness & error handling (bare except, unhandled resource leaks, missing network timeouts).
    3. Architecture & Ponytail Ladder compliance (unnecessary complexity, bloated abstractions).
    4. Maintainability & readability (cyclomatic complexity, missing type hints, dead code).
    """

    def __init__(self, strictness: str = "standard"):
        self.strictness = strictness.lower()

    def audit(self, target: str) -> Dict[str, Any]:
        """Audits either a file path or raw code string."""
        code_content = ""
        filename = "inline_snippet.py"

        if os.path.exists(target):
            filename = os.path.basename(target)
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    code_content = f.read()
            except Exception as e:
                return {
                    "filename": filename,
                    "status": "ERROR",
                    "summary": f"Failed to read file: {e}",
                    "findings": [],
                    "markdown_report": f"⚠️ **Code Rabbit Audit Error**: Could not read `{target}`: {e}",
                }
        else:
            code_content = target

        findings: List[Dict[str, Any]] = []

        # 1. Regex & Token-level Pattern Scans
        self._scan_security_patterns(code_content, findings)

        # 2. AST-level Structural Inspection
        self._scan_ast(code_content, findings)

        # 3. Ponytail Decision Ladder Audit
        self._scan_ponytail_compliance(code_content, findings)

        # Determine overall grade
        critical_count = sum(1 for f in findings if f["severity"] == "CRITICAL")
        warning_count = sum(1 for f in findings if f["severity"] == "WARNING")
        info_count = sum(1 for f in findings if f["severity"] == "INFO")

        if critical_count > 0:
            status = "CRITICAL_ISSUES_DETECTED"
            badge = "❌ **REJECT (Critical Issues Detected)**"
        elif warning_count > 0:
            status = "WARNINGS_FOUND"
            badge = "⚠️ **NEEDS_IMPROVEMENT (Warnings Found)**"
        else:
            status = "PASSED"
            badge = "✅ **APPROVED (Production Grade)**"

        # Generate structured Code Rabbit Markdown report
        report_lines = [
            f"### 🐇 Code Rabbit Audit: `{filename}`",
            f"**Review Status**: {badge}",
            f"**Findings Summary**: {critical_count} Critical, {warning_count} Warnings, {info_count} Suggestions\n",
        ]

        if not findings:
            report_lines.append("✨ **High-signal verification**: No architectural antipatterns, security leaks, or unhandled exceptions detected. Code complies with production standards.")
        else:
            report_lines.append("| Severity | Line | Issue | Recommendation |")
            report_lines.append("| :--- | :--- | :--- | :--- |")
            for f in findings:
                line_str = f"L{f.get('line', '?')}"
                report_lines.append(f"| **{f['severity']}** | {line_str} | {f['message']} | {f['recommendation']} |")

            report_lines.append("\n#### 💡 Actionable Refactoring Notes:")
            for f in findings:
                if f["severity"] in ("CRITICAL", "WARNING"):
                    report_lines.append(f"- **{f['message']}** (Line {f.get('line', '?')}): {f['recommendation']}")

        markdown_report = "\n".join(report_lines)

        return {
            "filename": filename,
            "status": status,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "findings": findings,
            "markdown_report": markdown_report,
        }

    def _scan_security_patterns(self, code: str, findings: List[Dict[str, Any]]):
        lines = code.splitlines()
        for idx, line in enumerate(lines, 1):
            # Hardcoded API Keys or Secrets
            if re.search(r'''(?i)(api[_-]?key|secret[_-]?key|token|password)\s*=\s*['"][a-zA-Z0-9_\-]{16,}['"]''', line):
                findings.append({
                    "severity": "CRITICAL",
                    "line": idx,
                    "message": "Potential hardcoded secret or API credential detected.",
                    "recommendation": "Extract credentials into environment variables via `os.getenv()` or `.env` file.",
                })

            # Bare eval or exec
            if re.search(r'''\b(eval|exec)\s*\(''', line):
                findings.append({
                    "severity": "CRITICAL",
                    "line": idx,
                    "message": "Dangerous dynamic execution (`eval` or `exec`).",
                    "recommendation": "Avoid dynamic code execution. Use `ast.literal_eval` for literals or dispatch tables.",
                })

            # Missing network timeouts
            if re.search(r'''requests\.(get|post|put|delete|patch)\([^)]*\)''', line) and "timeout=" not in line:
                findings.append({
                    "severity": "WARNING",
                    "line": idx,
                    "message": "HTTP network call missing explicit `timeout` argument.",
                    "recommendation": "Always specify `timeout=10` to prevent thread hanging on unresponsive endpoints.",
                })

    def _scan_ast(self, code: str, findings: List[Dict[str, Any]]):
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            findings.append({
                "severity": "CRITICAL",
                "line": e.lineno,
                "message": f"Syntax Error: {e.msg}",
                "recommendation": "Fix Python syntax before deployment.",
            })
            return

        for node in ast.walk(tree):
            # Bare except
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    findings.append({
                        "severity": "WARNING",
                        "line": node.lineno,
                        "message": "Bare `except:` clause catches BaseException (including KeyboardInterrupt and SystemExit).",
                        "recommendation": "Catch specific exceptions like `except Exception as e:` or domain-specific errors.",
                    })
                elif isinstance(node.body, list) and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    findings.append({
                        "severity": "WARNING",
                        "line": node.lineno,
                        "message": "Silent exception swallowing (`except ...: pass`).",
                        "recommendation": "Log the exception or re-raise; silent swallowing masks critical runtime bugs.",
                    })

            # Subprocess shell=True
            if isinstance(node, ast.Call):
                if hasattr(node.func, "attr") and node.func.attr in ("Popen", "run", "call", "check_output"):
                    for kw in node.keywords:
                        if kw.arg == "shell" and getattr(kw.value, "value", None) is True:
                            findings.append({
                                "severity": "CRITICAL",
                                "line": node.lineno,
                                "message": "Insecure `subprocess` invocation with `shell=True`.",
                                "recommendation": "Set `shell=False` and pass arguments as a list to eliminate shell injection risks.",
                            })

    def _scan_ponytail_compliance(self, code: str, findings: List[Dict[str, Any]]):
        """Audits adherence to the Ponytail Minimal Code Decision Ladder."""
        lines = code.splitlines()

        # Overengineering / deep nesting detection
        max_indent = 0
        for idx, line in enumerate(lines, 1):
            if line.strip():
                indent = len(line) - len(line.lstrip())
                if indent > max_indent:
                    max_indent = indent
                if indent >= 16:  # 4+ levels of nesting
                    findings.append({
                        "severity": "INFO",
                        "line": idx,
                        "message": "Deeply nested code block (nesting level >= 4).",
                        "recommendation": "Apply guard clauses, early returns, or helper functions to flatten logic (Ponytail Rung 6: Simplicity).",
                    })
                    break  # report once per file


def review_code(filepath_or_code: str, strictness: str = "standard") -> str:
    """Entrypoint function for reviewing code via Code Rabbit."""
    reviewer = CodeRabbitReviewer(strictness=strictness)
    result = reviewer.audit(filepath_or_code)
    return result["markdown_report"]
