"""
satellite_hud/satellite_app.py
Desktop floating companion launcher for Z.A.I.N.E Satellite HUD.
Opens http://127.0.0.1:7860/hud in a 400x480 frameless floating satellite window.
Uses pywebview if installed, otherwise opens system browser.
"""

import os
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

HUD_URL = os.getenv("ZAINE_HUD_URL", "http://127.0.0.1:7860/hud")


def wait_for_core(timeout_s: float = 10.0) -> bool:
    """Checks if core service HTTP daemon is active."""
    start_t = time.time()
    while time.time() - start_t < timeout_s:
        try:
            with urllib.request.urlopen("http://127.0.0.1:7860/api/health", timeout=1.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def launch_satellite_hud():
    print(f"Connecting Satellite HUD to {HUD_URL}...")
    if not wait_for_core(timeout_s=3.0):
        print("[WARN] Core service (:7860) not detected yet. Launching window in standby.")

    try:
        import webview
        print("Launching native WebView2 Satellite Window...")
        window = webview.create_window(
            title="Z.A.I.N.E Satellite HUD",
            url=HUD_URL,
            width=400,
            height=490,
            resizable=False,
            on_top=True,
            frameless=False
        )
        webview.start()
    except ImportError:
        print("[NOTICE] 'pywebview' not installed. Opening Satellite HUD in default browser...")
        webbrowser.open(HUD_URL)


if __name__ == "__main__":
    launch_satellite_hud()

