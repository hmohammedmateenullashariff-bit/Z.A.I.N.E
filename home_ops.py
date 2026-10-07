"""
Z.A.I.N.E — Phase 9: Autonomous Home & Dev Ops Sentinel Daemon
Continuous local service watchdog, memory database self-healing, automated backups,
and system telemetry guardian for Zaine.
"""

import os
import time
import sqlite3
import datetime
import urllib.request
import json
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "zaine_tasks.db"
BACKUP_DIR = PROJECT_ROOT / "data" / "backups"


def check_ollama_health() -> Dict[str, Any]:
    """Inspects local Ollama instance, listing installed models and responsiveness."""
    url = "http://localhost:11434/api/tags"
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Zaine-HomeOps/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            latency_ms = round((time.time() - t0) * 1000, 1)
            models = [m.get("name") for m in data.get("models", [])]
            return {
                "status": "ONLINE",
                "latency_ms": latency_ms,
                "models_available": models,
                "model_count": len(models)
            }
    except Exception as e:
        return {
            "status": "OFFLINE_OR_BUSY",
            "error": str(e),
            "latency_ms": None,
            "models_available": []
        }


def check_database_health() -> Dict[str, Any]:
    """Runs PRAGMA integrity check, measures size, table row counts, and status."""
    if not DB_PATH.exists():
        return {"status": "MISSING", "path": str(DB_PATH)}

    size_kb = round(DB_PATH.stat().st_size / 1024, 2)
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        integrity = cursor.fetchone()[0]

        # Count records across main tables in active zaine_tasks.db
        tables = {}
        for tbl in ["tasks", "memories", "task_learnings", "reminders", "conversation_episodes", "enrolled_faces", "telegram_chat_settings"]:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {tbl};")
                tables[tbl] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                tables[tbl] = 0

        conn.close()
        return {
            "status": "HEALTHY" if integrity == "ok" else "CORRUPTED",
            "integrity": integrity,
            "size_kb": size_kb,
            "table_counts": tables
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e),
            "size_kb": size_kb
        }


def backup_database(max_backups: int = 7) -> str:
    """
    Creates a consistent timestamped copy of zaine_tasks.db.
    Maintains a rolling window of recent backups.
    """
    if not DB_PATH.exists():
        return "Database file does not exist to back up."

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"zaine_tasks_{timestamp}.db"

    try:
        # Use sqlite backup API for non-blocking live backup
        src = sqlite3.connect(str(DB_PATH))
        dst = sqlite3.connect(str(backup_file))
        with dst:
            src.backup(dst, pages=100)
        dst.close()
        src.close()

        # Prune old backups exceeding max_backups
        backups = sorted(BACKUP_DIR.glob("zaine_tasks_*.db"), key=os.path.getmtime)
        while len(backups) > max_backups:
            oldest = backups.pop(0)
            try:
                oldest.unlink()
            except Exception:
                pass

        size_kb = round(backup_file.stat().st_size / 1024, 2)
        return f"Successfully created backup at {backup_file.name} ({size_kb} KB). Total retained backups: {len(backups)+1}."
    except Exception as e:
        return f"Database backup failed: {e}"


def perform_database_maintenance() -> str:
    """Executes WAL checkpoint and VACUUM to defragment memory store."""
    if not DB_PATH.exists():
        return "Database does not exist."
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.execute("VACUUM;")
        conn.close()
        new_size_kb = round(DB_PATH.stat().st_size / 1024, 2)
        return f"Database maintenance completed successfully. Current optimized size: {new_size_kb} KB."
    except Exception as e:
        return f"Database maintenance encountered: {e}"


def get_system_telemetry() -> Dict[str, Any]:
    """Gathers CPU, memory, disk, and process telemetry."""
    try:
        import psutil
        cpu_pct = psutil.cpu_percent(interval=0.2)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage(str(PROJECT_ROOT))

        # Check active python workers
        active_processes = []
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmd = " ".join(p.info.get('cmdline') or [])
                if any(k in cmd for k in ["simulate_training", "zaine_cascade", "overnight_autonomous"]):
                    active_processes.append({
                        "pid": p.info['pid'],
                        "cmd": p.info.get('cmdline', [''])[1:3]
                    })
            except Exception:
                pass

        return {
            "cpu_percent": cpu_pct,
            "ram_percent": ram.percent,
            "ram_used_gb": round(ram.used / (1024**3), 2),
            "ram_total_gb": round(ram.total / (1024**3), 2),
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "tracked_daemons": active_processes
        }
    except Exception as e:
        return {"error": str(e)}


def generate_devops_report() -> str:
    """Returns a formatted British-cadenced DevOps status report for Sir."""
    ollama = check_ollama_health()
    db = check_database_health()
    telemetry = get_system_telemetry()

    report_lines = [
        "==================================================================",
        "  Z.A.I.N.E — SYSTEM & HOME DEVOPS TELEMETRY REPORT",
        f"  Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "==================================================================",
        f"Neural Core (Ollama):  {ollama.get('status')} (Latency: {ollama.get('latency_ms')} ms)",
        f"Active Models:         {', '.join(ollama.get('models_available', []))}",
        "------------------------------------------------------------------",
        f"Cognitive Database:    {db.get('status')} (Integrity: {db.get('integrity', 'N/A')}, Size: {db.get('size_kb')} KB)",
        f"Learned Lessons:       {db.get('table_counts', {}).get('task_learnings', 0)} experiential records",
        f"Saved Memories:        {db.get('table_counts', {}).get('memories', 0)} permanent facts",
        f"Recorded Episodes:     {db.get('table_counts', {}).get('conversation_episodes', 0)} sessions",
        f"Active Tasks:          {db.get('table_counts', {}).get('tasks', 0)} tasks",
        f"Enrolled Faces:        {db.get('table_counts', {}).get('enrolled_faces', 0)} biometric profiles",
        "------------------------------------------------------------------",
        f"System CPU:            {telemetry.get('cpu_percent')}%",
        f"System RAM:            {telemetry.get('ram_used_gb')} / {telemetry.get('ram_total_gb')} GB ({telemetry.get('ram_percent')}%)",
        f"Disk Free:             {telemetry.get('disk_free_gb')} GB remaining",
        f"Tracked Daemons:       {len(telemetry.get('tracked_daemons', []))} active background pipelines",
        "=================================================================="
    ]
    return "\n".join(report_lines)


if __name__ == "__main__":
    print(generate_devops_report())
    print("\nTesting automated backup...")
    res = backup_database()
    print(res)
    print("\nTesting database maintenance...")
    res_maint = perform_database_maintenance()
    print(res_maint)
