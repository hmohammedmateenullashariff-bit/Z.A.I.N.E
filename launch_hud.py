"""
Launches the Z.A.I.N.E Holographic Web HUD server without opening an OS window.
Permits headless testing, DOM inspection, and API verification.
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import ZaineAgent
from ui import ZaineUI

def main():
    print("[HUD Launcher]: Initializing ZaineAgent...")
    agent = ZaineAgent()
    print("[HUD Launcher]: Initializing ZaineUI...")
    ui = ZaineUI(agent=agent, port=7860)
    ui.start_server()
    print(f"[HUD Launcher Ready]: http://127.0.0.1:{ui.port}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[HUD Launcher]: Stopping...")
        ui.stop()

if __name__ == "__main__":
    main()
