"""
scripts/ensure_core.py
Makes sure a Z.A.I.N.E core is running with the settings the launcher asked for, then waits until
its model is warm. Used by run_demo.bat / run_demo_fast.bat.

Why: the launchers used to reuse any core already listening on the port. A core started earlier with
other settings (7B instead of fast 3B, no ZAINE_DEMO approvals, a different workspace) was silently
kept, so the demo ran with the wrong model and without the guardrails it advertised.

Exit codes: 0 ready, 1 core failed to start/warm, 2 a mismatched core is embedded in another window.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_FILE = PROJECT_ROOT / ".zaine_core.json"
LOG_FILE = PROJECT_ROOT / "data" / "core_service.log"
READY_TIMEOUT_S = 180


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def wanted_config() -> dict:
    """Mirror of core_service.core_runtime_config() computed from this launcher's environment."""
    ws = os.getenv("ZAINE_WORKSPACE", "").strip()
    workspace = Path(ws).resolve() if ws else (PROJECT_ROOT / "workspace").resolve()
    return {
        "fast": _flag("ZAINE_FAST"),
        "demo": _flag("ZAINE_DEMO"),
        "single_model": _flag("ZAINE_SINGLE_MODEL", "1"),
        "num_ctx": int(os.getenv("ZAINE_NUM_CTX", "4096") or 4096),
        "workspace": str(workspace),
    }


def differences(running: dict, wanted: dict) -> list:
    diffs = []
    for key, want in wanted.items():
        have = running.get(key)
        if key == "workspace" and have is not None:
            same = os.path.normcase(os.path.normpath(str(have))) == os.path.normcase(os.path.normpath(str(want)))
        else:
            same = have == want
        if not same:
            diffs.append(f"{key}: running={have!r} wanted={want!r}")
    return diffs


def core_url() -> str:
    try:
        data = json.loads(CORE_FILE.read_text(encoding="utf-8"))
        if data.get("status") != "offline":
            return f"http://127.0.0.1:{data.get('port', 7860)}"
    except Exception:
        pass
    return "http://127.0.0.1:7860"


def get_status(url: str, timeout: float = 2.0):
    try:
        with urllib.request.urlopen(f"{url}/api/status", timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None


def stop_core(pid: int) -> bool:
    """Stops a standalone core_service.py process. Refuses anything else (e.g. a TUI hosting a core)."""
    import psutil
    try:
        proc = psutil.Process(pid)
        cmd = " ".join(proc.cmdline())
    except Exception:
        return True  # already gone
    if "core_service.py" not in cmd:
        print(f"  !! The running core (PID {pid}) lives inside another program:\n     {cmd}")
        print("     Close that Zaine window, then start this launcher again.")
        return False
    print(f"  -> Stopping core PID {pid} ...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except psutil.TimeoutExpired:
        proc.kill()
    return True


def start_core() -> subprocess.Popen:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "a", encoding="utf-8")
    log.write(f"\n===== core start {time.strftime('%Y-%m-%d %H:%M:%S')} config={json.dumps(wanted_config())}\n")
    log.flush()
    # Output goes to a log file: a core printing into the console the TUI draws on corrupts the screen.
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200) | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    return subprocess.Popen([sys.executable, "core_service.py"], cwd=str(PROJECT_ROOT),
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            creationflags=flags)


def wait_ready(proc) -> bool:
    start = time.time()
    shown = False
    while time.time() - start < READY_TIMEOUT_S:
        if proc is not None and proc.poll() is not None:
            print(f"  !! core_service.py exited with code {proc.returncode}. Last log lines:")
            try:
                for line in LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]:
                    print("     " + line)
            except Exception:
                pass
            return False
        status = get_status(core_url())
        if status:
            if status.get("model_loaded") and not status.get("warming"):
                print(f"  -> Core ready: {status.get('active_model')} on :{status.get('port')} "
                      f"(fast={status.get('config', {}).get('fast')}, demo={status.get('config', {}).get('demo')})")
                return True
            if not status.get("warming") and not status.get("model_loaded") and time.time() - start > 20:
                print("  !! Core is up but no model is loaded (is Ollama running and the model installed?).")
                return False
        if not shown:
            print("  -> Waiting for the model to load into VRAM ...")
            shown = True
        time.sleep(1)
    print(f"  !! Core not ready after {READY_TIMEOUT_S}s. See {LOG_FILE}")
    return False


def main() -> int:
    wanted = wanted_config()
    status = get_status(core_url())
    if status:
        diffs = differences(status.get("config") or {}, wanted)
        if not diffs:
            print("  -> Core already running with the requested settings.")
            return 0 if wait_ready(None) else 1
        print("  -> A core is running with different settings:")
        for d in diffs:
            print(f"     {d}")
        if not stop_core(int(status.get("pid") or 0)):
            return 2
        # Wait for the port to be released before starting the replacement.
        for _ in range(20):
            if not get_status(core_url(), timeout=0.5):
                break
            time.sleep(0.5)
    print("  -> Starting core_service.py (log: data/core_service.log) ...")
    return 0 if wait_ready(start_core()) else 1


if __name__ == "__main__":
    sys.exit(main())
