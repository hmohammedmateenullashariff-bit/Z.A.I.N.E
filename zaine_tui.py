"""
Z.A.I.N.E Neural Terminal User Interface Entry Point
Stage 1: Full-screen Textual TUI Skeleton & UI/UX Layout
Usage: python zaine_tui.py
"""

import os
import sys
from zaine_env import running_under_tests
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

    if not online and not running_under_tests():
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


def wait_for_readiness(timeout: float = 120.0) -> bool:
    """Waits for CoreService and model pre-warm to complete, printing visible message while waiting."""
    import time
    import httpx
    url = get_core_service_url()
    start_t = time.time()
    msg_printed = False
    while time.time() - start_t < timeout:
        try:
            resp = httpx.get(f"{url}/api/status", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                warming = data.get("warming", False)
                model_loaded = data.get("model_loaded", False)
                if warming or not model_loaded:
                    if not msg_printed:
                        model_label = "zaine-fast-3b" if os.getenv("ZAINE_FAST", "0").lower() in ("1", "true", "yes") else "zaine-reflex-7b"
                        print(f"[Z.A.I.N.E] Pre-warming reflex model ({model_label})... Waiting for readiness...")
                        msg_printed = True
                    time.sleep(0.5)
                    continue
                if msg_printed:
                    print("[Z.A.I.N.E] Reflex model ready.")
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> None:
    """Launch the Z.A.I.N.E Textual TUI Application."""
    core_svc = ensure_core_service()
    if not running_under_tests():
        wait_for_readiness()
    try:
        app = ZaineTUI()
        app.run()
    finally:
        if sys.platform == "win32":
            try:
                sys.stdout.write("\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?1015l\x1b[?1049l\x1b[?25h")
                sys.stdout.flush()
            except Exception:
                pass
        if core_svc:
            try:
                core_svc.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
