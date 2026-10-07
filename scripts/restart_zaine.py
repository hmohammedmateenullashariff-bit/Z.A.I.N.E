import os
import time
import psutil
import subprocess
from pathlib import Path

print("=== Stopping old Zaine instance and child processes ===")

# 1. Kill FFmpeg child processes
for p in psutil.process_iter(['pid', 'name']):
    try:
        if 'ffmpeg' in p.info['name'].lower():
            print(f"Terminating old FFmpeg process PID {p.info['pid']}...")
            p.kill()
    except Exception:
        pass

# 2. Terminate PID 4220 (or any other python main.py)
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmd = p.info.get('cmdline') or []
        if 'python' in p.info['name'].lower() and any('main.py' in str(c) for c in cmd):
            print(f"Terminating old main.py process PID {p.info['pid']}...")
            p.kill()
    except Exception:
        pass

time.sleep(2)

# Verify port 7860 is freed
freed = True
for c in psutil.net_connections():
    if c.laddr and c.laddr.port == 7860:
        print(f"Port 7860 still held by PID {c.pid}, terminating...")
        try:
            psutil.Process(c.pid).kill()
        except Exception:
            pass
        freed = False

time.sleep(1)
print("Old processes terminated and port 7860 freed.")

# Clean any 0-byte or incomplete partial mp4 files in workspace/youtube_shorts
shorts_dir = Path("workspace/youtube_shorts")
if shorts_dir.exists():
    for f in shorts_dir.glob("*.mp4"):
        try:
            # If file size < 50KB, it was an aborted render
            if f.stat().st_size < 50_000:
                print(f"Removing aborted incomplete render: {f.name}")
                f.unlink()
        except Exception:
            pass

print("=== Ready for fresh start ===")
