"""
ollama_profiler.py
Centralized instrumentation for logging all Ollama HTTP inference calls across Z.A.I.N.E.
Captures: caller, model, options (num_ctx, num_predict, keep_alive),
load_duration, prompt_eval_count, eval_count, and wall time.
"""

import threading
import time
from typing import Any, Dict, List, Optional

_lock = threading.Lock()
_recent_calls: List[Dict[str, Any]] = []


def log_ollama_call(
    caller: str,
    model: str,
    options: Optional[Dict[str, Any]],
    response_data: Optional[Dict[str, Any]],
    wall_time_s: float,
    keep_alive: Any = None,
) -> Dict[str, Any]:
    """
    Standardized logger for Ollama generation, chat, and embedding API calls.
    Extracts telemetry from Ollama response metadata and prints a uniform log line.
    """
    resp = response_data or {}
    opts = dict(options or {})
    if keep_alive is not None and "keep_alive" not in opts:
        opts["keep_alive"] = keep_alive

    num_ctx = opts.get("num_ctx", "default")
    num_predict = opts.get("num_predict", "default")
    ka = opts.get("keep_alive", "default")

    load_dur_ns = resp.get("load_duration", 0) or 0
    prompt_eval_count = resp.get("prompt_eval_count", 0) or 0
    prompt_eval_dur_ns = resp.get("prompt_eval_duration", 0) or 0
    eval_count = resp.get("eval_count", 0) or 0
    eval_dur_ns = resp.get("eval_duration", 0) or 0
    total_dur_ns = resp.get("total_duration", 0) or 0

    load_dur_s = round(load_dur_ns / 1e9, 3)
    p_eval_s = round(prompt_eval_dur_ns / 1e9, 3)
    eval_s = round(eval_dur_ns / 1e9, 3)
    total_dur_s = round(total_dur_ns / 1e9, 3)
    wall_s = round(wall_time_s, 2)

    entry = {
        "timestamp": time.time(),
        "caller": caller,
        "model": model,
        "options": {
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "keep_alive": ka,
        },
        "load_duration_s": load_dur_s,
        "prompt_eval_count": prompt_eval_count,
        "prompt_eval_duration_s": p_eval_s,
        "eval_count": eval_count,
        "eval_duration_s": eval_s,
        "total_duration_s": total_dur_s,
        "wall_time_s": wall_s,
    }

    with _lock:
        _recent_calls.append(entry)

    print(
        f"[OLLAMA_CALL] caller={caller} | model={model} | "
        f"options=(num_ctx={num_ctx}, num_predict={num_predict}, keep_alive={ka}) | "
        f"load_dur={load_dur_s}s | prompt_eval={prompt_eval_count} ({p_eval_s}s) | "
        f"eval={eval_count} ({eval_s}s) | wall={wall_s}s",
        flush=True,
    )
    return entry


def get_recent_calls() -> List[Dict[str, Any]]:
    """Returns a copy of logged Ollama call entries."""
    with _lock:
        return list(_recent_calls)


def clear_recent_calls() -> None:
    """Clears the recorded Ollama call history."""
    with _lock:
        _recent_calls.clear()
