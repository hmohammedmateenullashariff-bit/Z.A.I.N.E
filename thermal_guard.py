"""
Z.A.I.N.E — Autonomous Thermal Guardian & Workspace Sanitation Engine
- Real-time hardware temperature benchmarking via Windows ACPI ThermalZone counters
- Thermal safeguard protocol: pauses inference if CPU benchmark exceeds threshold (82°C)
  and cools down until safe threshold (68°C) is restored before resuming
- Workspace cleanliness: purges orphaned temporary files, caches, and duplicates
"""

import time
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parent

# Thermal Benchmark Thresholds (Celsius)
THERMAL_BENCHMARK_CRITICAL = 82.0   # Trigger temporary cooldown
THERMAL_BENCHMARK_SAFE = 68.0       # Resume normal operations
MAX_COOLDOWN_SECONDS = 300          # 5 minutes maximum cooldown


def get_cpu_temperature_celsius() -> Optional[float]:
    """
    Reads hardware temperature in Celsius via Windows ACPI ThermalZone counters.
    Returns None if hardware counters are unavailable.
    """
    try:
        cmd = [
            "powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Temperature"
        ]
        res = subprocess.check_output(cmd, text=True, timeout=5).strip()
        if res:
            first_val = float(res.split()[0])
            # Values around 300-400 are in Kelvin
            if first_val > 200:
                celsius = round(first_val - 273.15, 1)
                return celsius
            elif first_val > 0:
                return round(first_val, 1)
    except Exception:
        pass
    return None


def get_thermal_telemetry() -> Dict[str, Any]:
    """Returns complete thermal status and CPU load."""
    temp_c = get_cpu_temperature_celsius()
    try:
        import psutil
        cpu_load = psutil.cpu_percent(interval=0.1)
    except Exception:
        cpu_load = 0.0

    status = "NOMINAL"
    if temp_c is not None:
        if temp_c >= THERMAL_BENCHMARK_CRITICAL:
            status = "CRITICAL_HOT"
        elif temp_c >= 78.0:
            status = "ELEVATED"
    elif cpu_load >= 95.0:
        status = "HIGH_CPU_LOAD"

    return {
        "temperature_celsius": temp_c,
        "cpu_percent": cpu_load,
        "status": status,
        "critical_threshold": THERMAL_BENCHMARK_CRITICAL,
        "safe_threshold": THERMAL_BENCHMARK_SAFE
    }


def wait_for_thermal_cooldown(log_fn=print):
    """
    Blocks execution gracefully if temperature benchmark is breached,
    allowing the system fans and heat sink to restore safe operating temperatures.
    """
    telemetry = get_thermal_telemetry()
    temp = telemetry.get("temperature_celsius")

    if temp is not None and temp >= THERMAL_BENCHMARK_CRITICAL:
        log_fn(f"\n[THERMAL SAFEGUARD TRIGGERED] CPU temperature reached {temp}°C (Threshold: {THERMAL_BENCHMARK_CRITICAL}°C).")
        log_fn("  Pausing Z.A.I.N.E inference to protect hardware and avoid thermal throttling...")

        t0 = time.time()
        while time.time() - t0 < MAX_COOLDOWN_SECONDS:
            time.sleep(15)
            curr = get_cpu_temperature_celsius()
            log_fn(f"  [Cooling Sentinel] Current Temperature: {curr}°C | Target: <={THERMAL_BENCHMARK_SAFE}°C")
            if curr is not None and curr <= THERMAL_BENCHMARK_SAFE:
                log_fn(f"[THERMAL SAFEGUARD NORMALIZED] System cooled to {curr}°C. Resuming Z.A.I.N.E operations.")
                return True

        log_fn("[THERMAL SAFEGUARD] Maximum cooldown elapsed. Resuming under monitored state.")
        return True
    return False


def clean_unwanted_files() -> List[str]:
    """
    Deletes unwanted temporary files, compiler artifacts, caches, and duplicate files
    across Project-Z to keep the directory clean, lean, and organized.
    """
    deleted = []

    # 1. Purge all __pycache__ directories
    for pycache in PROJECT_ROOT.glob("**/__pycache__"):
        try:
            shutil.rmtree(pycache, ignore_errors=True)
            deleted.append(f"Directory: {pycache.relative_to(PROJECT_ROOT)}")
        except Exception:
            pass

    # 2. Purge file extensions: .pyc, .pyo, .tmp, .temp, .swp, ~*
    junk_patterns = ["**/*.pyc", "**/*.pyo", "**/*.tmp", "**/*.temp", "**/*.swp", "**/*~", "**/.DS_Store", "**/Thumbs.db"]
    for pat in junk_patterns:
        for f in PROJECT_ROOT.glob(pat):
            if f.is_file():
                try:
                    f.unlink()
                    deleted.append(f"File: {f.relative_to(PROJECT_ROOT)}")
                except Exception:
                    pass

    # 3. Clean duplicate script in workspace if present
    ws_duplicate = PROJECT_ROOT / "workspace" / "simulate_training.py"
    if ws_duplicate.exists():
        try:
            ws_duplicate.unlink()
            deleted.append("Duplicate: workspace/simulate_training.py")
        except Exception:
            pass

    # 4. Clean old test mp3 files in data/voice_cache older than 1 hour (keep cache light)
    vcache = PROJECT_ROOT / "data" / "voice_cache"
    if vcache.exists():
        now = time.time()
        for audio in vcache.glob("*.mp3"):
            if now - audio.stat().st_mtime > 3600:
                try:
                    audio.unlink()
                    deleted.append(f"Cache audio: {audio.name}")
                except Exception:
                    pass

    return deleted


if __name__ == "__main__":
    print("Testing Thermal Guardian & Workspace Sanitation...")
    status = get_thermal_telemetry()
    print("Thermal Telemetry:", status)
    print("\nRunning workspace sanitation...")
    cleaned = clean_unwanted_files()
    print(f"Cleaned {len(cleaned)} unwanted items:")
    for item in cleaned[:10]:
        print(" -", item)
    if len(cleaned) > 10:
        print(f" ... and {len(cleaned) - 10} more.")
