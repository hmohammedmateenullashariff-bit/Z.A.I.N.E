"""
Z.A.I.N.E — Autonomous Overnight System Sentinel & Thermal Watchdog
Monitors system health, temperatures, memory pressure, and Zaine processes
continuously until 06:05 AM IST.
"""

import os
import sys
import time
import psutil
import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from thermal_guard import get_cpu_temperature_celsius, clean_unwanted_files

LOG_PATH = PROJECT_ROOT / "data" / "overnight_watchdog.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        try:
            print(line.encode("ascii", "replace").decode("ascii"), flush=True)
        except Exception:
            pass
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run_watchdog():
    log("=== Overnight Watchdog Sentinel Online ===")
    log("Monitoring system safety, thermal health, and Zaine processes until 06:05 AM IST.")

    prev_ffmpeg_running = True

    while True:
        now = datetime.datetime.now()
        
        # Stop condition: 06:05 AM IST
        if now.hour == 6 and now.minute >= 5:
            log("=== Morning 06:05 AM Reached: Overnight Watchdog Shift Complete ===")
            break

        # 1. Hardware Telemetry
        temp_c = get_cpu_temperature_celsius()
        cpu_pct = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        disk_free_gb = disk.free / (1024 ** 3)

        temp_str = f"{temp_c:.1f}°C" if temp_c is not None else "N/A"
        log(f"Telemetry: CPU Temp: {temp_str} | CPU: {cpu_pct}% | RAM: {ram.percent}% ({ram.used/(1024**3):.1f}GB/{ram.total/(1024**3):.1f}GB) | C: Free: {disk_free_gb:.2f}GB")

        # 2. Thermal Guard Alert
        if temp_c is not None and temp_c >= 80.0:
            log(f"⚠️ [THERMAL ALERT]: CPU temperature is elevated at {temp_c}°C!")

        # 3. Disk Space Sentinel
        if disk_free_gb < 3.0:
            log(f"⚠️ [LOW DISK WARNING]: Free space is {disk_free_gb:.2f}GB (< 3.0GB threshold). Running emergency sanitation...")
            cleaned = clean_unwanted_files()
            log(f"  Sanitation removed {len(cleaned)} temporary items.")

        # 4. Check FFmpeg Render Status
        ffmpeg_active = False
        for p in psutil.process_iter(['name']):
            try:
                if 'ffmpeg' in (p.info['name'] or '').lower():
                    ffmpeg_active = True
                    break
            except Exception:
                pass

        if prev_ffmpeg_running and not ffmpeg_active:
            log("[RENDER COMPLETE]: Active FFmpeg rendering finished! High RAM allocation has been released back to OS.")
        prev_ffmpeg_running = ffmpeg_active

        # Sleep interval (60 seconds)
        time.sleep(60)


if __name__ == "__main__":
    run_watchdog()
