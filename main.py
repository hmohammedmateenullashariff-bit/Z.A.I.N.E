"""
Z.A.I.N.E. — Sovereign Autonomous AI Assistant
Primary Entry Point: Terminal-First / Agentic TUI Architecture

Architecture:
- The Terminal / TUI is the authoritative, primary interface for Z.A.I.N.E.
- Headless Core Service runs in background hosting ZaineAgent, memory, and tools.
- External integrations (Telegram bridge, Heartbeat sentinel) run headlessly.
- Voice is strictly command-driven and DISABLED by default (/voice on, /speak).
- Desktop GUI / Electron / browser windows have been permanently retired.

Usage:
    python main.py
"""

import os
import sys
import time
import threading
import requests
from pathlib import Path
from dotenv import load_dotenv

# Reconfigure stdout/stderr for full UTF-8 Unicode support on Windows 11
if sys.platform == "win32":
    try:
        os.system("")  # Enable Virtual Terminal Processing in Windows Console
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from agent import ZaineAgent
from core_service import CoreService, set_active_core_service
from heartbeat import heartbeat_daemon
from terminal_ui import run_terminal_cli
import voice


def ensure_ollama_ready():
    """Verifies Ollama is responsive; auto-launches with correct OLLAMA_MODELS if offline."""
    models_dir = r"E:\ollama\models" if Path(r"E:\ollama\models").exists() else (r"D:\ollama\models" if Path(r"D:\ollama\models").exists() else None)
    if models_dir and "OLLAMA_MODELS" not in os.environ:
        os.environ["OLLAMA_MODELS"] = models_dir

    try:
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=1.5)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    print("[Z.A.I.N.E]: Local Ollama service offline. Initializing daemon with local models...")
    try:
        import subprocess
        env = os.environ.copy()
        if models_dir:
            env["OLLAMA_MODELS"] = models_dir
        cmd = ["ollama", "serve"]
        subprocess.Popen(
            cmd,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(15):
            time.sleep(0.5)
            try:
                r = requests.get("http://127.0.0.1:11434/api/tags", timeout=1.0)
                if r.status_code == 200:
                    print("[Z.A.I.N.E]: Ollama neural daemon connected and online.")
                    return True
            except Exception:
                continue
    except Exception as e:
        print(f"[Z.A.I.N.E Warning]: Could not auto-launch Ollama: {e}")
    return False


def main():
    print("\n[Z.A.I.N.E]: Initializing autonomous neural core...")

    # 0. Ensure Ollama neural backend is online and configured
    ensure_ollama_ready()

    # 1. Instantiate Core Agent
    agent = ZaineAgent()

    # 2. Start Headless Core HTTP Service (hosts port 7860 for thin clients)
    core_service = CoreService(agent=agent, port=7860)
    core_service.start_server()
    set_active_core_service(core_service)

    # 3. Fast health verification gate (bounded 3s check)
    health_url = f"http://127.0.0.1:{core_service.port}/api/health"
    healthy = False
    for _ in range(15):
        try:
            r = requests.get(health_url, timeout=0.5)
            if r.status_code == 200 and r.json().get("ok"):
                healthy = True
                break
        except Exception:
            time.sleep(0.2)

    if not healthy:
        print(f"[Z.A.I.N.E Warning]: Core service health gate warning on {health_url}. Proceeding with in-process binding.")

    # 4. Start Telegram Bridge in background if token is configured
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if tg_token:
        try:
            from telegram_bridge import TelegramBridge
            bridge = TelegramBridge()
            threading.Thread(target=bridge.run_polling, daemon=True, name="TelegramBridgeThread").start()
            print("[Pocket Zaine]: Telegram background bridge activated.")
        except Exception as e:
            print(f"[Pocket Zaine]: Failed to start Telegram bridge: {e}")

    # 5. Start Proactive Heartbeat Daemon in background
    try:
        heartbeat_daemon.start()
    except Exception as e:
        print(f"[Heartbeat Sentinel Notice]: {e}")

    # 6. Voice Safety Verification: Voice MUST be explicitly OFF by default
    voice.disable_voice()

    # 7. Hand over to Terminal / TUI (Primary Authoritative User Interface)
    try:
        run_terminal_cli(core_service=core_service)
    finally:
        # Graceful Shutdown
        print("\n[Z.A.I.N.E Core]: Shutting down systems gracefully...")
        try:
            voice.disable_voice()
        except Exception:
            pass
        try:
            heartbeat_daemon.stop()
        except Exception:
            pass
        try:
            core_service.stop()
        except Exception:
            pass
        print("[Z.A.I.N.E Core]: All systems powered down safely. Standby, Sir.\n")


if __name__ == "__main__":
    main()
