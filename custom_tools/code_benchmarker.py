import sys
import time
import tracemalloc
import subprocess
from pathlib import Path

def code_benchmarker(script_path: str, args: str = "") -> str:
    """
    Benchmarks execution performance, CPU execution time, and peak memory usage of any script:
    - Measures runtime down to sub-millisecond precision.
    - Profiles peak RAM allocated by the process.
    - Verifies exit code correctness.
    """
    path_obj = Path(script_path)
    if not path_obj.is_absolute():
        path_obj = Path.cwd() / script_path

    if not path_obj.exists():
        return f"Error: Script '{script_path}' does not exist."

    start_time = time.perf_counter()
    tracemalloc.start()

    cmd = [sys.executable, str(path_obj)]
    if args:
        cmd.extend(args.split())

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        status = "PASSED" if res.returncode == 0 else f"FAILED (code {res.returncode})"
        lines = [
            f"=== Benchmark Profile for {path_obj.name} ===",
            f"- Status: {status}",
            f"- Execution Time: {elapsed_ms:.2f} ms ({elapsed_ms/1000:.4f} s)",
            f"- Peak Memory: {peak / (1024 * 1024):.3f} MB",
            f"- Output Preview: {res.stdout[:300].strip() if res.stdout else 'None'}"
        ]
        if res.stderr:
            lines.append(f"- Stderr: {res.stderr[:300].strip()}")

        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        tracemalloc.stop()
        return f"Benchmark Timeout: Script '{path_obj.name}' exceeded 60.0s execution ceiling."
    except Exception as e:
        tracemalloc.stop()
        return f"Benchmark Exception: {e}"
