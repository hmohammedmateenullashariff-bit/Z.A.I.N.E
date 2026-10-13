"""
Z.A.I.N.E Live Telemetry Collector & Micro-Sparkline Engine
Gathers 100% REAL system, memory, and hardware metrics.
Maintains rolling histories and non-blocking background snapshots for HUD rendering.
"""

import os
import shutil
import threading
import subprocess
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SPARK_CHARS = " ▂▃▄▅▆▇█"

_lock = threading.Lock()
_vram_history = deque([0.0] * 8, maxlen=16)
_cpu_history = deque([0.0] * 8, maxlen=16)
_throughput_history = deque([0.0] * 8, maxlen=16)


def make_sparkline(
    values: Sequence[float],
    min_val: float = 0.0,
    max_val: Optional[float] = None,
    length: int = 8,
) -> str:
    """
    Renders an ASCII/block micro-sparkline mapping numeric values to  ▂▃▄▅▆▇█.
    Pads to `length` if values has fewer items. Truncates to last `length` items if more.
    """
    if not values:
        return " " * length

    recent = list(values[-length:])
    if len(recent) < length:
        recent = [0.0] * (length - len(recent)) + recent

    hi = max_val if max_val is not None else (max(recent) if max(recent) > 0 else 1.0)
    lo = min_val
    span = max(hi - lo, 1e-6)

    chars = []
    for v in recent:
        clamped = max(lo, min(hi, v))
        ratio = (clamped - lo) / span
        idx = int(round(ratio * (len(SPARK_CHARS) - 1)))
        idx = max(0, min(len(SPARK_CHARS) - 1, idx))
        chars.append(SPARK_CHARS[idx])
    return "".join(chars)


def record_throughput_sample(tok_per_sec: float) -> None:
    """Records an instantaneous tokens/sec measurement for the live sparkline."""
    with _lock:
        _throughput_history.append(float(tok_per_sec))


def record_vram_sample(used_gb: float) -> None:
    """Records a VRAM measurement for the live sparkline."""
    with _lock:
        _vram_history.append(float(used_gb))


def get_throughput_sparkline(length: int = 8) -> str:
    """Returns the current throughput micro-sparkline."""
    with _lock:
        vals = list(_throughput_history)
    max_rate = max(max(vals, default=1.0), 30.0)
    return make_sparkline(vals, min_val=0.0, max_val=max_rate, length=length)


@dataclass
class TelemetrySnapshot:
    """Structured immutable hardware and memory telemetry snapshot."""
    cpu: str = "n/a"
    cpu_percent: float = 0.0
    cpu_sparkline: str = "        "
    ram: str = "n/a"
    ram_percent: float = 0.0
    vram: str = "n/a"
    vram_available: bool = False
    vram_used_mb: float = 0.0
    vram_total_mb: float = 4096.0
    vram_used_gb: float = 0.0
    vram_total_gb: float = 4.0
    vram_display: str = "n/a"
    gpu_name: str = "n/a"
    gpu_temp_c: float = 0.0
    vram_sparkline: str = "        "
    throughput_sparkline: str = "        "
    vault_status: str = "Connected"
    vault_notes: int = 0
    context_budget: int = 2000


_cached_snapshot: TelemetrySnapshot = TelemetrySnapshot()


def get_vram_info() -> Dict[str, Any]:
    """Reads real GPU memory via nvidia-smi if available."""
    nvsmi = shutil.which("nvidia-smi")
    if not nvsmi:
        return {"available": False, "used_mb": 0, "total_mb": 0, "name": "n/a", "temp_c": 0, "display": "n/a"}

    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,temperature.gpu,name", "--format=csv,noheader,nounits"],
            timeout=1.5,
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        lines = out.splitlines()
        if lines:
            parts = [p.strip() for p in lines[0].split(",")]
            if len(parts) >= 4:
                used = float(parts[0])
                total = float(parts[1])
                temp = float(parts[2])
                name = parts[3]
                return {
                    "available": True,
                    "used_mb": used,
                    "total_mb": total,
                    "temp_c": temp,
                    "name": name,
                    "display": f"{used / 1024:.1f} GB / {total / 1024:.1f} GB ({name})"
                }
    except Exception:
        pass
    return {"available": False, "used_mb": 0, "total_mb": 0, "temp_c": 0, "name": "n/a", "display": "n/a"}


def get_system_hardware() -> Dict[str, Any]:
    """Reads real CPU and RAM utilization using psutil."""
    cpu_percent = "n/a"
    cpu_val = 0.0
    ram_display = "n/a"
    ram_percent = "n/a"
    ram_val = 0.0

    try:
        import psutil
        cpu_val = psutil.cpu_percent(interval=None)
        cpu_percent = f"{cpu_val:.1f}%"
        vm = psutil.virtual_memory()
        used_gb = vm.used / (1024**3)
        total_gb = vm.total / (1024**3)
        ram_val = float(vm.percent)
        ram_percent = f"{ram_val:.0f}%"
        ram_display = f"{used_gb:.1f} / {total_gb:.1f} GB ({ram_val:.0f}%)"
    except Exception:
        pass

    return {
        "cpu": cpu_percent,
        "cpu_val": cpu_val,
        "ram": ram_display,
        "ram_percent": ram_percent,
        "ram_val": ram_val
    }


def get_vault_stats() -> Dict[str, Any]:
    """Reads real Obsidian vault statistics via MemoryManager."""
    try:
        from memory_manager import get_memory_manager
        mm = get_memory_manager()
        stats = mm.get_stats()
        obs = stats.get("obsidian", {})
        available = obs.get("available", False)
        folders = obs.get("folders", {})
        total_notes = sum(folders.values()) if folders else 0
        budget = stats.get("context_budget", {})
        max_chars = budget.get("max_chars", 2000)

        return {
            "available": available,
            "total_notes": total_notes,
            "status": "Connected" if available else "Offline",
            "max_chars": max_chars,
            "folders": folders
        }
    except Exception:
        return {
            "available": False,
            "total_notes": 0,
            "status": "n/a",
            "max_chars": 2000,
            "folders": {}
        }


def get_tool_registry_count() -> Any:
    """Returns real count of registered tools, or 'n/a' if unavailable."""
    try:
        from tools import TOOL_REGISTRY
        return len(TOOL_REGISTRY)
    except Exception:
        return "n/a"


def poll_hardware_telemetry() -> TelemetrySnapshot:
    """
    Executes a comprehensive, non-blocking telemetry sample.
    Updates rolling history buffers and refreshes cached snapshot.
    Designed to be called inside an async worker thread.
    """
    global _cached_snapshot

    hw = get_system_hardware()
    vram = get_vram_info()
    v_stats = get_vault_stats()

    cpu_val = hw.get("cpu_val", 0.0)
    with _lock:
        _cpu_history.append(cpu_val)
        cpu_hist = list(_cpu_history)
        if vram.get("available"):
            _vram_history.append(vram["used_mb"] / 1024.0)
        vram_hist = list(_vram_history)
        tp_hist = list(_throughput_history)

    cpu_spark = make_sparkline(cpu_hist, min_val=0.0, max_val=100.0, length=8)
    vram_total_gb = (vram.get("total_mb", 4096.0) / 1024.0) if vram.get("available") else 4.0
    vram_used_gb = (vram.get("used_mb", 0.0) / 1024.0) if vram.get("available") else 0.0
    vram_spark = make_sparkline(vram_hist, min_val=0.0, max_val=vram_total_gb, length=8)
    max_tp = max(max(tp_hist, default=1.0), 30.0)
    tp_spark = make_sparkline(tp_hist, min_val=0.0, max_val=max_tp, length=8)

    snapshot = TelemetrySnapshot(
        cpu=hw["cpu"],
        cpu_percent=cpu_val,
        cpu_sparkline=cpu_spark,
        ram=hw["ram"],
        ram_percent=hw.get("ram_val", 0.0),
        vram=vram.get("display", "n/a"),
        vram_available=vram["available"],
        vram_used_mb=vram["used_mb"],
        vram_total_mb=vram["total_mb"],
        vram_used_gb=vram_used_gb,
        vram_total_gb=vram_total_gb,
        vram_display=vram["display"],
        gpu_name=vram.get("name", "n/a"),
        gpu_temp_c=vram.get("temp_c", 0.0),
        vram_sparkline=vram_spark,
        throughput_sparkline=tp_spark,
        vault_status=v_stats["status"],
        vault_notes=v_stats["total_notes"],
        context_budget=v_stats["max_chars"],
    )

    with _lock:
        _cached_snapshot = snapshot

    return snapshot


def get_cached_telemetry() -> TelemetrySnapshot:
    """Returns the latest cached snapshot with zero subprocess overhead."""
    with _lock:
        return _cached_snapshot
