"""
Z.A.I.N.E — Autonomous Cognitive Simulation & Self-Play Trainer
Simulates realistic multi-domain conversations with Zaine, exercises tool orchestration,
triggers background meta-cognition learning, and exports training trajectories to JSONL.
"""

import sys
import os
import json
import time
import argparse
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

if (Path(__file__).resolve().parent / "agent.py").exists():
    PROJECT_ROOT = Path(__file__).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import ZaineAgent

SIMULATION_BANK = [
    # 1. Coding & Algorithms
    "Write a python script called quick_sort.py in workspace that sorts a list of 10 random integers and run it.",
    "Can you create a utility in workspace to check if a word is an anagram and test it?",
    "Build a python script in workspace that calculates the greatest common divisor of two numbers.",
    "Help me write a script in workspace that parses a json string and prints all its keys.",
    "Write a python script in workspace that converts seconds into hours, minutes, and seconds.",

    # 2. Cascade & Software Engineering
    "Inspect the demo.py file in workspace and tell me what methods it contains.",
    "Let's write a unit test for MathUtils in demo.py inside workspace and run it.",
    "Can you check all files currently located in the workspace directory?",
    "Run the demo.py script in workspace and report if there are any runtime errors.",
    "Refactor demo.py in workspace to add a cube method and verify it.",

    # 3. Public APIs & Live Data
    "What is the current weather forecast in London right now?",
    "Can you check the current live price of Ethereum in USD and INR?",
    "Convert 150 Euros to US Dollars using current forex rates.",
    "What is the exact definition and phonetic pronunciation of the word 'resilience'?",
    "What is the current price of Bitcoin today?",

    # 4. System Diagnostics & Telemetry
    "Zaine, what is my current system status including CPU, RAM, and battery levels?",
    "Check if my laptop is currently running on battery or plugged into power.",
    "Give me an executive report on system health and storage capacity on drive C.",
    "Check how much RAM is free before I run my local compilation.",
    "Run a diagnostic check on system resources.",

    # 5. Productivity & Second Brain
    "Add a note to my second brain vault titled 'Architecture Meeting' with content 'Discussed microservices and Qwen 7B migration.'",
    "Search my personal vault for any notes related to 'Architecture'.",
    "List all notes currently stored in my second brain vault.",
    "Add a task to my agenda: 'Review pull request for API integration' with priority High in category Work.",
    "Set a reminder for me in 30 minutes to drink water and take a stretch break.",

    # 6. Etiquette & Salutation
    "Good morning Zaine, how are all systems performing today?",
    "Hello Zaine, introduce yourself and explain your primary capabilities.",
    "Thank you for your assistance today, Zaine.",
    "Zaine, who created you and what is your primary mission?",
    "How do you ensure zero-cost local execution on this workstation?",

    # 7. Media & Desktop Automation
    "Play Clair de Lune by Debussy on YouTube.",
    "Open YouTube in the browser for me.",
    "Skip the current ad playing on YouTube.",
    "Open Visual Studio Code so we can work on the project.",
    "Check if there are any unread emails in my inbox.",

    # 8. Web Development
    "Create an interactive countdown timer in workspace with index.html and start a local server.",
    "Build a modern responsive card layout in workspace/card.html and verify it.",
    "Write a simple Python HTTP request test in workspace/api_check.py and run it.",
    "Create a clean CSS stylesheet in workspace/style.css with dark glassmorphism variables.",
    "List all workspace files to make sure our web assets are organized.",

    # 9. Multilingual & Nuance
    "Zaine, kya sab kuch theek chal raha hai system me?",
    "Aap kaise hain Zaine? Kya aap ready hain?",
    "Zaine, can you summarize the main advantages of local AI over cloud APIs?",
    "Mujhe aaj ke top priorities batao jo database me hain.",
    "Zaine, explain quantum superposition in two concise sentences.",

    # 10. Complex Multi-Step Tasks
    "Check the weather in Tokyo and tell me if I would need an umbrella today.",
    "Search the vault for any meeting notes, then check my pending tasks.",
    "Check system health, and if CPU is below 80 percent, let me know all systems are green.",
    "Find the word definition of 'serendipity' and save it as a note in my vault.",
    "Check the price of Bitcoin, convert 100 USD to INR, and give me a brief market summary."
]


def run_simulation(count: int = 10, cooling_delay: float = 1.0, dataset_path: str = "data/simulated_conversations.jsonl"):
    print("\n==================================================================")
    print("  [*] Z.A.I.N.E  A U T O N O M O U S  S I M U L A T O R")
    print(f"  Exercising {count} Multi-Domain Scenarios & Meta-Cognition")
    print("==================================================================\n")

    os.makedirs(os.path.dirname(dataset_path), exist_ok=True)
    agent = ZaineAgent()
    scenarios = []
    while len(scenarios) < count:
        scenarios.extend(SIMULATION_BANK)
    scenarios = scenarios[:count]

    successful = 0
    start_time = time.time()

    with open(dataset_path, "a", encoding="utf-8") as f_out:
        for idx, prompt in enumerate(scenarios, start=1):
            print(f"[{idx}/{count}] Simulating Turn...", flush=True)
            print(f"  User Query: \"{prompt}\"", flush=True)
            t0 = time.time()
            try:
                reply = agent.chat(prompt)
                elapsed = time.time() - t0
                tool_used = getattr(agent, "last_tool_called", None)

                print(f"  Elapsed: {elapsed:.2f}s | Tool: [{tool_used or 'None'}]", flush=True)
                first_sentence = reply.split(". ")[0] if reply else ""
                print(f"  Zaine: {first_sentence}...", flush=True)

                # Record trajectory for continuous fine-tuning dataset
                entry = {
                    "iteration": idx,
                    "prompt": prompt,
                    "tool": tool_used,
                    "response": reply,
                    "elapsed_sec": round(elapsed, 2),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                f_out.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f_out.flush()
                successful += 1

            except Exception as e:
                print(f"  Error in simulation turn: {e}")

            print("------------------------------------------------------------------")
            if cooling_delay > 0:
                time.sleep(cooling_delay)

    total_elapsed = time.time() - start_time
    print("\n✅ Simulation Complete!")
    print(f"  Completed: {successful}/{count} conversations successfully.")
    print(f"  Total Duration: {total_elapsed:.1f}s (Average: {total_elapsed/max(successful, 1):.2f}s/turn)")
    print(f"  Trajectories Saved: {dataset_path}")
    print("  Z.A.I.N.E's cognitive memory has been updated with newly generated learnings.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zaine Autonomous Simulation Harness")
    parser.add_argument("--count", type=int, default=10, help="Number of conversations to simulate (default: 10)")
    parser.add_argument("--delay", type=float, default=1.0, help="Cooling delay between turns in seconds (default: 1.0)")
    parser.add_argument("--out", type=str, default="data/simulated_conversations.jsonl", help="Path to output JSONL dataset")
    args = parser.parse_args()

    run_simulation(count=args.count, cooling_delay=args.delay, dataset_path=args.out)
