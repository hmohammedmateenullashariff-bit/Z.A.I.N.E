"""
Z.A.I.N.E — Telegram Bridge 24/7 Supervisor Daemon
Runs Pocket Zaine as an autonomous persistent background daemon with auto-recovery.
"""

import sys
import time
from pathlib import Path

# Ensure project root in python path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from telegram_bridge import TelegramBridge


def run_daemon():
    print("[Telegram Daemon]: Starting Pocket Zaine supervisor...")
    while True:
        try:
            bridge = TelegramBridge()
            bridge.run_polling()
        except KeyboardInterrupt:
            print("\n[Telegram Daemon]: Stopped by user.")
            break
        except Exception as e:
            print(f"[Telegram Daemon Error]: {e}. Restarting in 5 seconds...")
            time.sleep(5)


if __name__ == "__main__":
    run_daemon()
