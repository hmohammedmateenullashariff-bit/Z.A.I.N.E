"""
scripts/ensure_ollama.py
Verifies that the Ollama neural daemon is running and has models loaded.
If Ollama is down, or running with an empty model catalog (e.g. Due to cross-drive junction
mount point restrictions in Go), this script restarts Ollama with OLLAMA_MODELS=D:\\ollama\\models
and waits until the model catalog is verified.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

DEFAULT_MODELS_DIR = "E:\\ollama\\models" if os.path.exists("E:\\ollama\\models") else ("D:\\ollama\\models" if os.path.exists("D:\\ollama\\models") else os.path.expanduser("~\\.ollama\\models"))
OLLAMA_URL = "http://127.0.0.1:11434"


def get_loaded_models(timeout: float = 2.0) -> list[str] | None:
    """Queries Ollama /api/tags and returns a list of model names, or None if unreachable."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                return models
    except Exception:
        return None
    return None


def restart_ollama_daemon(models_dir: str) -> bool:
    """Terminates stale ollama instances and launches ollama serve with explicit OLLAMA_MODELS."""
    # Kill any existing ollama processes
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "ollama.exe", "/IM", "ollama app.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception:
        pass

    time.sleep(1.0)

    # Prepare environment
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = models_dir

    # Flags for completely silent background detachment on Windows
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
    except FileNotFoundError:
        print("  !! [ERROR] 'ollama' executable not found in PATH.")
        return False
    except Exception as e:
        print(f"  !! [ERROR] Failed to spawn ollama serve: {e}")
        return False

    return True


def ensure_ollama(timeout_seconds: int = 20) -> bool:
    models_dir = os.environ.get("OLLAMA_MODELS", DEFAULT_MODELS_DIR)

    models = get_loaded_models(timeout=2.0)
    if models is not None and len(models) > 0:
        print(f"  -> Ollama is online ({len(models)} models ready).")
        return True

    if models is not None and len(models) == 0:
        print("  -> Ollama is running but reported 0 models (mount-point traversal issue).")
        print(f"  -> Re-launching daemon with OLLAMA_MODELS={models_dir} ...")
    else:
        print(f"  -> Ollama daemon not detected. Starting with OLLAMA_MODELS={models_dir} ...")

    if not restart_ollama_daemon(models_dir):
        return False

    # Wait for daemon to come online and discover models
    start = time.time()
    while time.time() - start < timeout_seconds:
        time.sleep(1.0)
        models = get_loaded_models(timeout=2.0)
        if models is not None and len(models) > 0:
            print(f"  -> Ollama neural daemon active ({len(models)} models ready).")
            return True

    print(f"  !! [ERROR] Ollama did not report ready models within {timeout_seconds}s.")
    return False


if __name__ == "__main__":
    success = ensure_ollama()
    sys.exit(0 if success else 1)

