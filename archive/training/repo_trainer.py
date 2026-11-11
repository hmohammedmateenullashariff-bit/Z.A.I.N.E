"""
Z.A.I.N.E — Autonomous 2-Hour Continuous Repository Training & Self-Distillation Engine
Executes structured cognitive tasks across all 17 developer repositories:
- The Algorithms (sorting, graphs, dynamic programming)
- Code Rabbit (code reviews, security scans, Ponytail Ladder checks)
- System Design Primer (CAP theorem, caching, capacity calculations)
- Build Your Own X (Git, Redis, Docker, compilers, web servers)
- Free For Dev (free tier hosting, databases, auth, CI/CD)
- Open Source Alternatives (Supabase, Penpot, PostHog, Meilisearch, SigNoz)
- Roadmap.sh (AI Engineer, Backend, DevOps roadmaps)
- Computer Science / OSSU (data structures, theory, discrete math)
- LLMs From Scratch (transformer mechanics, multi-head attention, RoPE, LoRA)
- ML From Scratch (NumPy linear regression, logistic, decision trees)
- Papers We Love (Raft consensus, MapReduce, Dynamo, Attention)
- Engineering Blogs & Best Websites for Programmers

Integrates:
- Hardware Thermal Benchmark Safeguards (Threshold: 82.0°C; auto-cooldown until <= 68.0°C)
- In-memory execution & workspace sanitation
- Cognitive Reflection & Knowledge Distillation into SQLite `task_learnings` & `vault/`
- Periodic 2-minute cooling and database maintenance breaks
"""

import sys
import os
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any

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
import thermal_guard
import home_ops
import memory
import vault

TRAINING_LOG = PROJECT_ROOT / "data" / "repo_training.log"
DATASET_PATH = PROJECT_ROOT / "data" / "repo_training_conversations.jsonl"
STATUS_FILE = PROJECT_ROOT / "data" / "repo_training_status.json"

# Curated, diverse task bank across all 17 repositories & 5 pillars
REPO_TASKS = [
    # --- Pillar A: Algorithms, Code Review & ML Primitives ---
    {
        "id": "algo_dijkstra",
        "domain": "The Algorithms",
        "pillar": "Pillar A: Autonomous Coding & Review",
        "prompt": "Look up Dijkstra's algorithm from TheAlgorithms. Explain its min-heap priority queue implementation and best-for use cases.",
        "expected_tool": "lookup_algorithm",
        "keywords": "dijkstra algorithm graph priority queue shortest path"
    },
    {
        "id": "coderabbit_security_audit",
        "domain": "Code Rabbit",
        "pillar": "Pillar A: Autonomous Coding & Review",
        "prompt": "Review this Python code snippet with Code Rabbit: `import os\ndef execute(cmd):\n    api_key = 'sk_live_998877665544332211'\n    eval(cmd)\n`",
        "expected_tool": "code_review",
        "keywords": "code review audit security vulnerability eval api key"
    },
    {
        "id": "algo_topological_sort",
        "domain": "The Algorithms",
        "pillar": "Pillar A: Autonomous Coding & Review",
        "prompt": "Lookup Topological Sort (Kahn's Algorithm) from TheAlgorithms and explain how in-degree tracking resolves DAG build dependencies.",
        "expected_tool": "lookup_algorithm",
        "keywords": "topological sort kahn dag in-degree build dependency"
    },
    {
        "id": "ml_linear_regression",
        "domain": "ML From Scratch",
        "pillar": "Pillar A: Autonomous Coding & Review",
        "prompt": "Search our developer knowledge for pure NumPy Linear Regression and explain the gradient descent update rules for weights and bias.",
        "expected_tool": "search_developer_knowledge",
        "keywords": "linear regression numpy gradient descent weights bias loss"
    },
    {
        "id": "coderabbit_resilience_check",
        "domain": "Code Rabbit",
        "pillar": "Pillar A: Autonomous Coding & Review",
        "prompt": "Run a Code Rabbit code review on a function that uses bare `except:` and makes HTTP requests without a timeout parameter.",
        "expected_tool": "code_review",
        "keywords": "code review timeout exception bare except resilience"
    },
    {
        "id": "algo_lru_cache",
        "domain": "The Algorithms",
        "pillar": "Pillar A: Autonomous Coding & Review",
        "prompt": "Lookup LRU Cache from TheAlgorithms. How does combining an OrderedDict or Doubly Linked List with a Hash Map achieve O(1) eviction?",
        "expected_tool": "lookup_algorithm",
        "keywords": "lru cache data structure eviction ordered dict hash map"
    },

    # --- Pillar B: System Design & Blueprints ---
    {
        "id": "sd_cap_pacelc",
        "domain": "System Design Primer",
        "pillar": "Pillar B: Systems Architecture & Deep Engineering",
        "prompt": "Advise on CAP Theorem and PACELC trade-offs using System Design Primer. When should an architect select CP vs AP systems?",
        "expected_tool": "system_design_advisor",
        "keywords": "cap theorem pacelc consistency availability partition tolerance"
    },
    {
        "id": "byox_redis",
        "domain": "Build Your Own X",
        "pillar": "Pillar B: Systems Architecture & Deep Engineering",
        "prompt": "Get the step-by-step architecture blueprint for building Redis from scratch. What are the 5 core implementation stages?",
        "expected_tool": "get_architecture_blueprint",
        "keywords": "redis blueprint resp event loop in-memory key-value"
    },
    {
        "id": "sd_caching_strategies",
        "domain": "System Design Primer",
        "pillar": "Pillar B: Systems Architecture & Deep Engineering",
        "prompt": "Provide system design guidance on Caching Strategies (Cache-Aside, Write-Through, Write-Behind) for a service handling 100M daily active users.",
        "expected_tool": "system_design_advisor",
        "keywords": "caching strategies cache-aside write-through write-behind redis"
    },
    {
        "id": "byox_docker",
        "domain": "Build Your Own X",
        "pillar": "Pillar B: Systems Architecture & Deep Engineering",
        "prompt": "What are the core Linux kernel primitives (namespaces, cgroups, chroot, overlayfs) needed to build Docker containers from scratch?",
        "expected_tool": "get_architecture_blueprint",
        "keywords": "docker container namespaces cgroups chroot isolation"
    },
    {
        "id": "sd_back_of_envelope",
        "domain": "System Design Primer",
        "pillar": "Pillar B: Systems Architecture & Deep Engineering",
        "prompt": "Give me the back-of-the-envelope estimation cheat sheet for computing QPS, storage, and latency from System Design Primer.",
        "expected_tool": "system_design_advisor",
        "keywords": "back of envelope estimation qps latency bandwidth storage"
    },
    {
        "id": "byox_git",
        "domain": "Build Your Own X",
        "pillar": "Pillar B: Systems Architecture & Deep Engineering",
        "prompt": "Explain how Git's content-addressable object store works (blobs, trees, commits, refs) based on Build Your Own X.",
        "expected_tool": "get_architecture_blueprint",
        "keywords": "git blueprint sha-1 blobs trees commits directed acyclic graph"
    },

    # --- Pillar C: Developer Ecosystem & Zero-Cost Infrastructure ---
    {
        "id": "oss_alt_firebase",
        "domain": "Open Source Alternatives",
        "pillar": "Pillar C: Developer Ecosystem & Zero-Cost",
        "prompt": "What are the top open-source, self-hostable alternatives to Firebase, and what are their sovereignty benefits?",
        "expected_tool": "find_oss_alternatives",
        "keywords": "firebase supabase appwrite pocketbase open source alternative"
    },
    {
        "id": "ffd_databases",
        "domain": "Free For Dev",
        "pillar": "Pillar C: Developer Ecosystem & Zero-Cost",
        "prompt": "Find free-tier managed databases for developers from Free For Dev. Which services offer free PostgreSQL and SQLite?",
        "expected_tool": "find_free_developer_services",
        "keywords": "free databases postgresql neon supabase turso free for dev"
    },
    {
        "id": "oss_alt_datadog",
        "domain": "Open Source Alternatives",
        "pillar": "Pillar C: Developer Ecosystem & Zero-Cost",
        "prompt": "Recommend open-source alternatives to Datadog for APM, metrics, and distributed tracing.",
        "expected_tool": "find_oss_alternatives",
        "keywords": "datadog signoz grafana open source alternatives observability"
    },
    {
        "id": "ffd_hosting",
        "domain": "Free For Dev",
        "pillar": "Pillar C: Developer Ecosystem & Zero-Cost",
        "prompt": "Find free developer cloud hosting and PaaS providers that support automatic Git deployments from Free For Dev.",
        "expected_tool": "find_free_developer_services",
        "keywords": "free hosting paas render fly.io vercel netlify free for dev"
    },

    # --- Pillar D: Career Mentorship, Roadmaps & Pedagogy ---
    {
        "id": "roadmap_ai_engineer",
        "domain": "Roadmap.sh",
        "pillar": "Pillar D: Career Mentorship & Hackathons",
        "prompt": "Retrieve the complete AI Engineer / LLM practitioner skill roadmap from Roadmap.sh.",
        "expected_tool": "get_career_roadmap",
        "keywords": "ai engineer roadmap llm transformers pytorch fine-tuning"
    },
    {
        "id": "cs_curriculum_ossu",
        "domain": "OSSU Computer Science",
        "pillar": "Pillar D: Career Mentorship & Hackathons",
        "prompt": "Search our developer knowledge for the core Computer Science curriculum from OSSU / MIT. What are the foundational subject areas?",
        "expected_tool": "search_developer_knowledge",
        "keywords": "ossu computer science mit curriculum programming systems theory"
    },
    {
        "id": "roadmap_backend",
        "domain": "Roadmap.sh",
        "pillar": "Pillar D: Career Mentorship & Hackathons",
        "prompt": "What are the key milestones on the Backend Engineer roadmap from Roadmap.sh?",
        "expected_tool": "get_career_roadmap",
        "keywords": "backend engineer roadmap networking databases caching messaging"
    },
    {
        "id": "dev_resources_books",
        "domain": "Free Programming Books & Sites",
        "pillar": "Pillar D: Career Mentorship & Hackathons",
        "prompt": "Search our developer knowledge for recommended free programming books and essential developer websites.",
        "expected_tool": "search_developer_knowledge",
        "keywords": "programming books websites devdocs roadmap overapi regex101"
    },

    # --- Pillar E: AI, LLMs & MLOps ---
    {
        "id": "llm_causal_attention",
        "domain": "LLMs From Scratch",
        "pillar": "Pillar E: AI, LLM & MLOps Mastery",
        "prompt": "Look up Multi-Head Causal Self-Attention from LLMs From Scratch and explain the role of the triangular causal attention mask.",
        "expected_tool": "lookup_llm_architecture",
        "keywords": "causal attention mask multi-head transformer pytorch llm"
    },
    {
        "id": "llm_lora_mechanics",
        "domain": "LLMs From Scratch",
        "pillar": "Pillar E: AI, LLM & MLOps Mastery",
        "prompt": "Explain the mechanics of LoRA (Low-Rank Adaptation) from LLMs From Scratch. How does low-rank matrix decomposition freeze base weights?",
        "expected_tool": "lookup_llm_architecture",
        "keywords": "lora low-rank adaptation fine-tuning matrix decomposition vram"
    },
    {
        "id": "paper_raft_consensus",
        "domain": "Papers We Love",
        "pillar": "Pillar E: AI, LLM & MLOps Mastery",
        "prompt": "Search our developer knowledge for the Raft consensus paper from Papers We Love. What was its major breakthrough over Paxos?",
        "expected_tool": "search_developer_knowledge",
        "keywords": "raft consensus paxos distributed systems leader election"
    },
    {
        "id": "paper_attention_transformer",
        "domain": "Papers We Love",
        "pillar": "Pillar E: AI, LLM & MLOps Mastery",
        "prompt": "Search developer knowledge for 'Attention Is All You Need' from Papers We Love and summarize its core contribution to generative AI.",
        "expected_tool": "search_developer_knowledge",
        "keywords": "attention is all you need vaswani transformer generative ai"
    }
]


def log(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    print(entry, flush=True)
    os.makedirs(TRAINING_LOG.parent, exist_ok=True)
    with open(TRAINING_LOG, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def update_status(data: Dict[str, Any]):
    os.makedirs(STATUS_FILE.parent, exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def run_repo_training_session(target_hours: float = 2.0):
    """
    Runs continuous repository training cycles for target_hours (default: 2.0 hrs = 7200 seconds).
    Monitors hardware thermals before every turn.
    Distills heuristics into task_learnings and notes into vault/.
    """
    start_time = time.time()
    target_seconds = target_hours * 3600.0
    end_time = start_time + target_seconds

    log("==================================================================")
    log("  Z.A.I.N.E AUTONOMOUS REPOSITORY TRAINING & EVOLUTION ENGINE")
    log(f"  Target Duration: {target_hours:.1f} Hours ({int(target_seconds)} seconds)")
    log("  Curriculum: 17 Developer Repositories across 5 Intelligence Pillars")
    log(f"  Thermal Safeguard Threshold: {thermal_guard.THERMAL_BENCHMARK_CRITICAL}°C (Safe: {thermal_guard.THERMAL_BENCHMARK_SAFE}°C)")
    log("==================================================================")

    # Sanitation at start
    purged = thermal_guard.clean_unwanted_files()
    log(f"Initial workspace sanitation completed ({len(purged)} items purged).")

    agent = ZaineAgent()
    total_turns_completed = 0
    total_lessons_learned = 0
    cycle_index = 1

    update_status({
        "status": "RUNNING",
        "started_at": datetime.datetime.now().isoformat(),
        "target_hours": target_hours,
        "turns_completed": 0,
        "lessons_distilled": 0,
        "percent_complete": 0.0,
        "last_updated": datetime.datetime.now().isoformat()
    })

    while time.time() < end_time:
        elapsed = time.time() - start_time
        remaining = max(0.0, end_time - time.time())
        pct = min(100.0, round((elapsed / target_seconds) * 100.0, 1))

        log("\n------------------------------------------------------------------")
        log(f"  CYCLE {cycle_index} | Elapsed: {int(elapsed/60)}m / {int(target_seconds/60)}m ({pct}%) | Remaining: {int(remaining/60)}m")
        log("------------------------------------------------------------------")

        # Shuffle or rotate through tasks
        for task_idx, task in enumerate(REPO_TASKS, 1):
            if time.time() >= end_time:
                break

            # 1. Thermal Benchmark Check
            thermal_guard.wait_for_thermal_cooldown(log_fn=log)

            prompt = task["prompt"]
            task_id = task["id"]
            domain = task["domain"]
            pillar = task["pillar"]

            # Alternate: Even cycles use Ultron Mode for aggressive cognitive execution!
            use_ultron = (cycle_index % 2 == 0)
            if use_ultron and not agent.ultron_mode:
                agent.handle_natural_language_triggers("activate ultron mode")
            elif not use_ultron and agent.ultron_mode:
                agent.handle_natural_language_triggers("stand down ultron")

            mode_tag = "[ULTRON MODE]" if agent.ultron_mode else "[JARVIS MODE]"
            log(f"  Turn {task_idx}/{len(REPO_TASKS)} {mode_tag} [{domain}]: \"{prompt[:65]}...\"")

            t_turn_start = time.time()
            try:
                reply = agent.chat(prompt)
                turn_elapsed = time.time() - t_turn_start
                tool_called = getattr(agent, "last_tool_called", None)
                log(f"    Elapsed: {turn_elapsed:.2f}s | Tool Executed: [{tool_called or 'None'}]")

                # 2. Record in training trajectory dataset
                record = {
                    "cycle": cycle_index,
                    "task_id": task_id,
                    "domain": domain,
                    "pillar": pillar,
                    "prompt": prompt,
                    "ultron_mode": agent.ultron_mode,
                    "tool": tool_called,
                    "response": reply[:400] + ("..." if len(reply) > 400 else ""),
                    "elapsed_sec": round(turn_elapsed, 2),
                    "timestamp": datetime.datetime.now().isoformat()
                }
                with open(DATASET_PATH, "a", encoding="utf-8") as f_out:
                    f_out.write(json.dumps(record, ensure_ascii=False) + "\n")

                # 3. Distill learning heuristic into SQLite task_learnings
                lesson = f"In {domain} ({pillar}), prioritize {tool_called or 'structured synthesis'} for {task['keywords'].split()[0]} tasks."
                memory.record_task_learning(
                    task_summary=f"Trained on {domain}: {task['id']}",
                    status="SUCCESS",
                    lesson_learned=lesson,
                    keywords=task["keywords"]
                )
                total_lessons_learned += 1
                total_turns_completed += 1

                # Update live status file
                update_status({
                    "status": "RUNNING",
                    "cycle": cycle_index,
                    "turns_completed": total_turns_completed,
                    "lessons_distilled": total_lessons_learned,
                    "percent_complete": min(100.0, round(((time.time() - start_time) / target_seconds) * 100.0, 1)),
                    "current_domain": domain,
                    "ultron_mode": agent.ultron_mode,
                    "temperature_celsius": thermal_guard.get_cpu_temperature_celsius(),
                    "last_updated": datetime.datetime.now().isoformat()
                })

            except Exception as e:
                log(f"    Error during turn: {e}")

            # Thermal safety pause between turns
            time.sleep(2.0)

        # Post-Cycle Interval (Every full pass across all 24 tasks takes ~3-4 minutes)
        # Execute maintenance, cleanup, and 90-second cooling pause
        log(f"\nCycle {cycle_index} complete ({total_turns_completed} total turns completed so far).")
        purged = thermal_guard.clean_unwanted_files()
        log(f"Cleaned {len(purged)} workspace artifacts.")
        
        # Add reflection note to Second Brain Vault every 2 cycles
        if cycle_index % 2 == 0:
            vault_title = f"Repo Evolution Milestone - Cycle {cycle_index}"
            vault_content = f"Completed cycle {cycle_index} of 17-repo training. Distilled {total_lessons_learned} heuristics across algorithms, system design, and AI architectures."
            try:
                vault.add_to_vault(vault_title, vault_content, category="Training", tags="evolution,repos,training")
                log("Archived milestone debrief into Second Brain Vault.")
            except Exception as e:
                log(f"Vault debrief note: {e}")

        # Short 60s cooldown to keep fans quiet and temps stable
        if time.time() < end_time:
            log("Taking 60-second thermal moderation pause before next cycle...")
            for s in range(4):
                time.sleep(15)
                temp = thermal_guard.get_cpu_temperature_celsius()
                log(f"  [Thermal Monitor] Temp: {temp}°C | CPU: {thermal_guard.get_thermal_telemetry().get('cpu_percent')}%")

        cycle_index += 1

    # Conclude session
    log("\n==================================================================")
    log("  2-HOUR REPOSITORY TRAINING COMPLETED SUCCESSFULLY!")
    log(f"  Total Cycles Completed: {cycle_index - 1}")
    log(f"  Total Interactive Turns: {total_turns_completed}")
    log(f"  Total Heuristics Distilled into Memory: {total_lessons_learned}")
    log("==================================================================")

    # Perform automated database backup
    backup_res = home_ops.backup_database()
    log(f"[Maintenance Backup] {backup_res}")

    update_status({
        "status": "COMPLETED",
        "finished_at": datetime.datetime.now().isoformat(),
        "total_cycles": cycle_index - 1,
        "turns_completed": total_turns_completed,
        "lessons_distilled": total_lessons_learned,
        "percent_complete": 100.0,
        "last_updated": datetime.datetime.now().isoformat()
    })


if __name__ == "__main__":
    duration_hrs = 2.0
    if len(sys.argv) > 1:
        try:
            duration_hrs = float(sys.argv[1])
        except ValueError:
            duration_hrs = 2.0
    run_repo_training_session(target_hours=duration_hrs)
