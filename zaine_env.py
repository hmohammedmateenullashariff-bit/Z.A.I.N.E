"""
zaine_env.py
Process-level runtime checks shared by core_service, the TUI and its widgets.
"""

import os
import sys


def running_under_tests() -> bool:
    """True when this process was launched by a test runner.

    Checking `"unittest" in sys.modules` is not reliable: ordinary third-party imports pulled in by
    core_service load unittest, which silently disabled background services in normal runs.
    So this inspects how the process was started instead.
    """
    if os.environ.get("ZAINE_TESTING", "").strip().lower() in ("1", "true", "yes"):
        return True
    if "PYTEST_CURRENT_TEST" in os.environ:
        return True
    argv0 = (sys.argv[0] if sys.argv else "").replace("\\", "/").lower()
    script = argv0.rsplit("/", 1)[-1]
    # `python -m unittest` rewrites argv[0] to "<python> -m unittest"; pytest's entry point contains "pytest".
    return "unittest" in argv0 or "pytest" in argv0 or script.startswith("test_")
