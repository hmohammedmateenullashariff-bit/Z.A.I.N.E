"""
Z.A.I.N.E Agent Terminal — Professional Agent Operating Environment
Direct CLI entry point for the transformed terminal-first UX.
Usage:
    python terminal.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from terminal_ui import run_terminal_cli, state

if __name__ == "__main__":
    # Check for CLI flags e.g. --code, --ultron, --verbose
    args = sys.argv[1:]
    if "--code" in args:
        state.mode = "code"
    if "--ultron" in args:
        state.persona = "ultron"
    if "--verbose" in args:
        state.verbosity = "verbose"
    elif "--compact" in args:
        state.verbosity = "compact"

    run_terminal_cli()
