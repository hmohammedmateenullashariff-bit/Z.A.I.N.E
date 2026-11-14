"""
scratch_audit/test_presentation_warm_run.py
Runs the exact same 7 presentation steps headlessly with models PRE-WARMED (warm execution).
"""

import os
import sys
import time
import json
import asyncio
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_service import CoreService
from tui.client import stream_chat_events, get_system_status, clear_context, StreamTimeoutError
from rich.console import Console
from rich.markdown import Markdown as RichMarkdown
from rich.panel import Panel
from rich.text import Text
from io import StringIO

PORT = 7891
BASE_URL = f"http://127.0.0.1:{PORT}"

async def run_chat_prompt(prompt_text: str):
    t_start = time.perf_counter()
    ttft = None
    chunks = []
    events = []
    error = None
    timeout_fired = False

    try:
        async for ev in stream_chat_events(prompt_text, base_url=BASE_URL):
            now = time.perf_counter()
            ev_type = ev.get("type")
            events.append(ev_type)
            if ev_type == "token":
                text = ev.get("content", "") or ev.get("text", "") or ev.get("token", "")
                chunks.append(text)
                if ttft is None:
                    ttft = now - t_start
            elif ev_type == "error":
                error = ev.get("message", "Unknown error")
    except StreamTimeoutError as e:
        timeout_fired = True
        error = f"StreamTimeoutError: {e}"
    except Exception as e:
        error = f"Exception: {type(e).__name__}: {e}"

    t_end = time.perf_counter()
    wall_time = t_end - t_start
    full_response = "".join(chunks)

    return {
        "prompt": prompt_text,
        "is_cold": False,
        "wall_time_s": round(wall_time, 2),
        "ttft_s": round(ttft, 2) if ttft is not None else None,
        "tokens_received": len(chunks),
        "events_count": len(events),
        "timeout_fired": timeout_fired,
        "error": error,
        "full_response": full_response,
        "response_preview": full_response[:120].strip()
    }

async def run_warm_presentation():
    print("=== STARTING WARM PRESENTATION DRY RUN ===", flush=True)
    srv = CoreService(port=PORT)
    srv.start_server()
    os.environ["ZAINE_AUTH_TOKEN"] = srv.auth_token
    time.sleep(1.5)

    steps_results = []

    try:
        # Step 1: Greeting (WARM)
        print("\n--- Step 1: Greeting (WARM) ---", flush=True)
        s1 = await run_chat_prompt("Good evening Zaine.")
        print(f"Result: Wall={s1['wall_time_s']}s, TTFT={s1['ttft_s']}s, Timeout={s1['timeout_fired']}, Error={s1['error']}", flush=True)
        steps_results.append({"step": 1, "name": "Greeting (Warm)", **s1})

        # Step 2: Person lookup ("Who is Alan Turing?")
        print("\n--- Step 2: Person Lookup (Vault Memory) ---", flush=True)
        s2 = await run_chat_prompt("Who is Alan Turing?")
        print(f"Result: Wall={s2['wall_time_s']}s, TTFT={s2['ttft_s']}s, Timeout={s2['timeout_fired']}, Error={s2['error']}", flush=True)
        steps_results.append({"step": 2, "name": "Person Lookup", **s2})

        # Step 3: Slash Command /status
        print("\n--- Step 3: Slash Command /status ---", flush=True)
        t0 = time.perf_counter()
        try:
            status_res = await get_system_status(BASE_URL)
            t_status = time.perf_counter() - t0
            s3 = {
                "step": 3,
                "name": "/status",
                "prompt": "/status",
                "wall_time_s": round(t_status, 2),
                "status": status_res.get("status", "unknown"),
                "active_model": status_res.get("active_model", "unknown"),
                "error": None
            }
        except Exception as e:
            t_status = time.perf_counter() - t0
            s3 = {
                "step": 3,
                "name": "/status",
                "prompt": "/status",
                "wall_time_s": round(t_status, 2),
                "error": str(e)
            }
        print(f"Result: Wall={s3['wall_time_s']}s, Status={s3.get('status')}, Error={s3['error']}", flush=True)
        steps_results.append(s3)

        # Step 4: Tool Request ("What is the current workstation CPU and RAM status?")
        print("\n--- Step 4: Tool Request (Workstation Status) ---", flush=True)
        s4 = await run_chat_prompt("What is the current workstation CPU and RAM status?")
        print(f"Result: Wall={s4['wall_time_s']}s, TTFT={s4['ttft_s']}s, Timeout={s4['timeout_fired']}, Error={s4['error']}", flush=True)
        steps_results.append({"step": 4, "name": "Tool Request", **s4})

        # Step 5: Code Request ("Write a python function to compute Fibonacci numbers.")
        print("\n--- Step 5: Code Request ---", flush=True)
        s5 = await run_chat_prompt("Write a python function to compute Fibonacci numbers.")
        print(f"Result: Wall={s5['wall_time_s']}s, TTFT={s5['ttft_s']}s, Timeout={s5['timeout_fired']}, Error={s5['error']}", flush=True)
        steps_results.append({"step": 5, "name": "Code Request", **s5})

        # Step 6: Slash Command /new
        print("\n--- Step 6: Slash Command /new ---", flush=True)
        t0 = time.perf_counter()
        try:
            new_res = await clear_context(BASE_URL)
            t_new = time.perf_counter() - t0
            s6 = {
                "step": 6,
                "name": "/new",
                "prompt": "/new",
                "wall_time_s": round(t_new, 2),
                "cleared": new_res.get("status") == "cleared" or "cleared" in str(new_res).lower(),
                "error": None
            }
        except Exception as e:
            t_new = time.perf_counter() - t0
            s6 = {
                "step": 6,
                "name": "/new",
                "prompt": "/new",
                "wall_time_s": round(t_new, 2),
                "error": str(e)
            }
        print(f"Result: Wall={s6['wall_time_s']}s, Cleared={s6.get('cleared')}, Error={s6['error']}", flush=True)
        steps_results.append(s6)

        # Step 7: Long answer
        print("\n--- Step 7: Long Answer + Code Block ---", flush=True)
        long_prompt = "Explain Python generators vs coroutines in detail and provide a complete producer-consumer asyncio code example with classes."
        s7 = await run_chat_prompt(long_prompt)

        test_text = s7.get("full_response") or s7.get("response_preview") or "No text received"
        md = RichMarkdown(test_text, code_theme="monokai", justify="left")
        panel = Panel(md, title="Z.A.I.N.E", border_style="cyan", expand=True)

        buf_80 = StringIO()
        c_80 = Console(file=buf_80, width=80, force_terminal=True)
        c_80.print(panel)
        lines_80 = buf_80.getvalue().splitlines()
        max_w_80 = max((len(Text.from_ansi(l).plain) for l in lines_80), default=0)
        overflow_80 = max_w_80 > 80

        buf_140 = StringIO()
        c_140 = Console(file=buf_140, width=140, force_terminal=True)
        c_140.print(panel)
        lines_140 = buf_140.getvalue().splitlines()
        max_w_140 = max((len(Text.from_ansi(l).plain) for l in lines_140), default=0)
        overflow_140 = max_w_140 > 140

        s7["render_80_col"] = {"max_line_width": max_w_80, "overflow": overflow_80, "line_count": len(lines_80)}
        s7["render_140_col"] = {"max_line_width": max_w_140, "overflow": overflow_140, "line_count": len(lines_140)}
        print(f"Result: Wall={s7['wall_time_s']}s, TTFT={s7['ttft_s']}s, 80col_max={max_w_80} (overflow={overflow_80}), 140col_max={max_w_140} (overflow={overflow_140})", flush=True)
        steps_results.append({"step": 7, "name": "Long Answer & Code Block", **s7})

    finally:
        try:
            srv.stop()
        except Exception:
            pass

    summary = {
        "warm_run_steps": steps_results,
        "total_demo_wall_s": round(sum(s.get("wall_time_s", 0) for s in steps_results), 2)
    }

    out_file = os.path.join(str(REPO_ROOT), "scratch_audit", "presentation_warm_run_results.json")
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== WARM DRY RUN COMPLETED ===", flush=True)
    print(f"Total Demo Duration: {summary['total_demo_wall_s']}s", flush=True)

if __name__ == "__main__":
    asyncio.run(run_warm_presentation())
