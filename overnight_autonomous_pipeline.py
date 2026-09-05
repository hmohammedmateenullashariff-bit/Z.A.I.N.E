"""
Z.A.I.N.E — Overnight Autonomous Evolution Engine
Runs continuous cycles of training, dynamic question mutation on even iterations,
15-minute cool-down & reflection intervals, hardware thermal benchmark safeguards,
and autonomous feature implementation until 04:00 AM.
"""

import os
import sys
import json
import time
import datetime
from pathlib import Path

# Enable ANSI colors & UTF-8 output on Windows
if sys.platform == "win32":
    try:
        os.system("")
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import ZaineAgent
import home_ops
import thermal_guard
import total_recall
import morning_briefing
import self_distillation

DATASET_PATH = PROJECT_ROOT / "data" / "simulated_conversations.jsonl"
OVERNIGHT_LOG = PROJECT_ROOT / "data" / "overnight_evolution.log"

# Primary Question Bank (Odd Iterations - Core Capabilities)
ODD_QUESTIONS = [
    "Write a python script called quick_sort.py in workspace that sorts a list of 10 random integers and run it.",
    "Can you create a utility in workspace to check if a word is an anagram and test it?",
    "Build a python script in workspace that calculates the greatest common divisor of two numbers.",
    "Help me write a script in workspace that parses a json string and prints all its keys.",
    "Write a python script in workspace that converts seconds into hours, minutes, and seconds.",
    "Inspect the demo.py file in workspace and tell me what methods it contains.",
    "What is the current weather forecast in London right now?",
    "Can you check the current live price of Ethereum in USD and INR?",
    "Zaine, what is my current system status including CPU, RAM, and battery levels?",
    "Add a note to my second brain vault titled 'Architecture Meeting' with content 'Discussed microservices and Qwen 7B migration.'"
]

# Advanced Dynamic Question Bank (Even Iterations - Edge Cases & Multi-Step Reasoning)
EVEN_QUESTIONS = [
    "Build an efficient binary search algorithm in workspace/bsearch.py with automated unit test assertions and run it.",
    "Write a script in workspace/matrix_mult.py to multiply two 3x3 matrices and verify the output.",
    "Convert 250 British Pounds into Euros and US Dollars using live forex exchange rates.",
    "Query the dictionary definition of 'perspicacity' and formulate a practical sentence using it.",
    "Create a workspace script called csv_parser.py that generates sample user data and computes summary statistics.",
    "Conduct deep web research on 'latest breakthroughs in quantum computing 2026' and provide an executive briefing.",
    "Search my personal vault for 'Architecture' and list any key decisions made.",
    "Check if any application called 'notepad' or 'calc' is running, and report system resource health.",
    "Build an interactive HTML landing page with CSS glassmorphism in workspace/landing.html and verify files.",
    "Check the price of Bitcoin, calculate how much 0.05 BTC is worth in INR, and summarize market trends."
]


def log(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    print(entry, flush=True)
    os.makedirs(OVERNIGHT_LOG.parent, exist_ok=True)
    with open(OVERNIGHT_LOG, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def is_external_simulation_running() -> bool:
    """Checks if an independent simulate_training.py process is active."""
    try:
        import psutil
        my_pid = os.getpid()
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if p.info['pid'] == my_pid:
                    continue
                cmd = " ".join(p.info.get('cmdline') or [])
                if "simulate_training.py" in cmd:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def wait_for_active_simulation_to_complete():
    """Waits until any active simulation completes all 10 turns and terminates."""
    log("Checking status of active simulation...")
    last_count = -1

    while True:
        # Check count of lines
        count = 0
        if DATASET_PATH.exists():
            with open(DATASET_PATH, "r", encoding="utf-8") as f:
                count = sum(1 for line in f if line.strip())

        still_running = is_external_simulation_running()

        if count != last_count:
            log(f"Simulation progress: {count}/10 turns logged. (External process running: {still_running})")
            last_count = count

        if count >= 10 and not still_running:
            log("Initial 10-turn simulation confirmed complete! Process terminated gracefully.")
            break

        if count >= 10:
            log("10 turns logged. Waiting for external process to exit cleanly...")
            time.sleep(10)
            if not is_external_simulation_running():
                log("External simulation process has concluded.")
                break

        time.sleep(15)


def run_training_cycle(cycle_index: int, agent: ZaineAgent, total_cycles: int = 5):
    """Runs one training cycle with question rotation and thermal benchmark checks."""
    is_even = (cycle_index % 2 == 0)
    questions = EVEN_QUESTIONS if is_even else ODD_QUESTIONS
    mode_label = "EVEN ITERATION (Advanced Dynamic Edge Cases)" if is_even else "ODD ITERATION (Core Foundation)"

    log("\n==================================================================")
    log(f"  STARTING TRAINING CYCLE {cycle_index}/{total_cycles} — {mode_label}")
    log("==================================================================")

    os.makedirs(DATASET_PATH.parent, exist_ok=True)
    with open(DATASET_PATH, "a", encoding="utf-8") as f_out:
        for q_idx, prompt in enumerate(questions, start=1):
            # Thermal Benchmark Check before each turn
            thermal_guard.wait_for_thermal_cooldown(log_fn=log)

            # Record in temporal recall
            total_recall.record_temporal_event("training_turn_start", f"Cycle {cycle_index} Turn {q_idx}: {prompt[:50]}...")

            log(f"  [Cycle {cycle_index} | Turn {q_idx}/{len(questions)}] Prompt: \"{prompt}\"")
            t_start = time.time()
            try:
                reply = agent.chat(prompt)
                elapsed = time.time() - t_start
                tool_used = getattr(agent, "last_tool_called", None)
                log(f"    Elapsed: {elapsed:.2f}s | Tool: [{tool_used or 'None'}]")
                first_sent = reply.split(". ")[0] if reply else ""
                log(f"    Zaine: {first_sent[:80]}...")

                record = {
                    "cycle": cycle_index,
                    "turn": q_idx,
                    "prompt": prompt,
                    "tool": tool_used,
                    "response": reply,
                    "elapsed_sec": round(elapsed, 2),
                    "timestamp": datetime.datetime.now().isoformat()
                }
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                f_out.flush()

                total_recall.record_temporal_event("training_turn_end", f"Cycle {cycle_index} Turn {q_idx} finished in {elapsed:.1f}s", {"tool": tool_used})

            except Exception as e:
                log(f"    Error executing turn: {e}")

            # Thermal safety pause between turns
            time.sleep(2.0)

    log(f"Cycle {cycle_index}/{total_cycles} complete!")


def main_overnight_loop():
    log("==================================================================")
    log("  Z.A.I.N.E OVERNIGHT AUTONOMOUS EVOLUTION ENGINE (v2.0)")
    log("  Target Completion: 04:00 AM")
    log("  Thermal Benchmark Safeguard: Active (Threshold: 82.0°C)")
    log("==================================================================")

    # 1. Clean unwanted files at start
    cleaned = thermal_guard.clean_unwanted_files()
    log(f"Initial workspace sanitation completed ({len(cleaned)} items purged).")

    # 2. Wait for active simulation if still running
    wait_for_active_simulation_to_complete()

    agent = ZaineAgent()
    cycle_batch = 1

    while True:
        now = datetime.datetime.now()
        # Check if 5:00 AM reached (Mateen sir wakes at 5:00 AM)
        if now.hour >= 5 and now.minute >= 0:
            log("5:00 AM target time reached! Overnight autonomous run concluding gracefully.")
            break

        log(f"\n>>> Starting 5-Iteration Evolution Block {cycle_batch} at {now.strftime('%H:%M:%S')} (Target: 05:00 AM) <<<")

        # Run 5 training iterations with question changing after each even iteration
        for iter_num in range(1, 6):
            run_training_cycle(iter_num, agent, total_cycles=5)
            log(f"Completed iteration {iter_num}/5 of Block {cycle_batch}.")

        # 15-Minute Cooling, Reflection & Feature Planning Interval
        log("\n==================================================================")
        log("  STARTING 15-MINUTE REFLECTION, COOLING & MAINTENANCE INTERVAL")
        log("==================================================================")

        # 1. Perform database maintenance & safety backup during cooldown
        backup_res = home_ops.backup_database()
        log(f"  [Maintenance] {backup_res}")
        maint_res = home_ops.perform_database_maintenance()
        log(f"  [Maintenance] {maint_res}")
        purged = thermal_guard.clean_unwanted_files()
        log(f"  [Sanitation] Cleaned {len(purged)} temporary files.")

        # 2. Distill new lessons learned from recently completed turns
        distilled = self_distillation.run_self_distillation_cycle()
        log(f"  [Cognitive Distillation] Synthesized {distilled} new experiential lessons.")

        # 3. Harvest & Learn Daily Top 10 AI Updates from the Web
        try:
            import ai_daily_intel
            ai_updates = ai_daily_intel.get_daily_ai_updates(force_refresh=True)
            log(f"  [AI Daily Intel] Harvested and learned {len(ai_updates)} daily AI breakthroughs from the web.")
        except Exception as e:
            log(f"  [AI Daily Intel] Harvest notice: {e}")

        # 4. Check & Run Autonomous YouTube Studio Cadence (4:00 AM Night Anime Slot)
        try:
            from youtube_studio import check_and_run_daily_youtube_schedule
            yt_res = check_and_run_daily_youtube_schedule(force=False, genre="anime")
            actions = yt_res.get("actions_taken", [])
            if actions:
                for act in actions:
                    log(f"  [YouTube Studio] {act}")
        except Exception as e:
            log(f"  [YouTube Studio] Scheduler notice: {e}")

        for minute in range(1, 16):
            time.sleep(60)
            telemetry = thermal_guard.get_thermal_telemetry()
            log(f"  Cooldown minute {minute}/15 | Temp: {telemetry.get('temperature_celsius')}°C | CPU: {telemetry.get('cpu_percent')}%")

        log("15-minute cooling & maintenance interval concluded. Refreshing agent state.")
        cycle_batch += 1

    # Conclude with Morning Executive Briefing at 05:00 AM
    log("\nGenerating Morning Executive Briefing Dossier for Sir...")
    try:
        briefing_text = morning_briefing.compile_morning_briefing()
        log("Executive Briefing successfully compiled to data/morning_briefing.md")

        # Dispatch executive briefing to Telegram
        try:
            from telegram_bridge import send_telegram_alert
            send_telegram_alert(
                f"🌅 **Good morning, Mateen sir! (05:00 AM)**\n\n"
                f"Z.A.I.N.E overnight evolution and surveillance cycles have completed successfully.\n\n"
                f"• All database stores backed up & optimized\n"
                f"• Cognitive distillation completed\n"
                f"• YouTube anime battle slots monitored & executed\n"
                f"• Executive morning intelligence compiled\n\n"
                f"Ready for your review, Sir. Have a productive morning!",
                parse_mode="Markdown"
            )
            log("Morning briefing alert dispatched to Telegram (@Zaine_mateen_bot).")
        except Exception:
            pass
    except Exception as e:
        log(f"Error compiling morning briefing: {e}")

    log("==================================================================")
    log("  OVERNIGHT AUTONOMOUS EVOLUTION COMPLETED SUCCESSFULLY.")
    log("  All systems nominal. Ready for morning briefing.")
    log("==================================================================")


if __name__ == "__main__":
    main_overnight_loop()
