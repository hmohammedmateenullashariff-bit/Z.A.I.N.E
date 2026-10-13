"""
Z.A.I.N.E Neural Terminal User Interface Entry Point
Stage 1: Full-screen Textual TUI Skeleton & UI/UX Layout
Usage: python zaine_tui.py
"""

import sys
from pathlib import Path

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tui.app import ZaineTUI
from tui.client import get_core_service_url, check_backend_health


def ensure_core_service():
    """Auto-boots headless CoreService if offline so standalone TUI is always functional."""
    import time
    import asyncio
    url = get_core_service_url()
    try:
        online, _ = asyncio.run(check_backend_health(url))
    except Exception:
        online = False

    if not online and not ("unittest" in sys.modules or "pytest" in sys.modules):
        try:
            from core_service import get_core_service, CoreService, set_active_core_service
            active = get_core_service()
            if not active:
                active = CoreService(port=7860)
                active.start_server()
                set_active_core_service(active)
                time.sleep(0.4)
                return active
        except Exception:
            pass
    return None


def main() -> None:
    """Launch the Z.A.I.N.E Textual TUI Application."""
    core_svc = ensure_core_service()
    try:
        app = ZaineTUI()
        app.run()
    finally:
        if core_svc:
            try:
                core_svc.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
