"""
Z.A.I.N.E Phase 7 — Autonomous Multi-Agent Hive Mind
Coordinates specialist sub-agents (Coder, Researcher, System Guardian, Executive Planner)
using a shared blackboard and parallel task orchestration.
100% local, zero-cost, autonomous.
"""

import sys
import os
import time
from pathlib import Path
from typing import Dict, Any, List

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

import tools
import browser_agent


class HiveBlackboard:
    """Shared in-memory state and artifact repository for cooperating sub-agents."""
    def __init__(self):
        self.artifacts: Dict[str, Any] = {}
        self.logs: List[str] = []

    def set(self, key: str, value: Any):
        self.artifacts[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.artifacts.get(key, default)

    def log(self, agent_name: str, message: str):
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] [{agent_name}] {message}"
        self.logs.append(entry)


class CoderSubAgent:
    """Specialist sub-agent for code architecture, implementation, and test execution."""
    def __init__(self, blackboard: HiveBlackboard):
        self.blackboard = blackboard

    def execute(self, task_instruction: str, context: str = "") -> str:
        self.blackboard.log("CoderAgent", f"Starting code task: '{task_instruction[:60]}...'")
        code_out = tools.code_assistant(task_instruction, context_code=context)
        self.blackboard.set("latest_code", code_out)
        self.blackboard.log("CoderAgent", "Code synthesis completed.")
        return code_out


class ResearcherSubAgent:
    """Specialist sub-agent for deep web research, documentation scraping, and live data."""
    def __init__(self, blackboard: HiveBlackboard):
        self.blackboard = blackboard

    def execute(self, research_query: str) -> str:
        self.blackboard.log("ResearchAgent", f"Gathering intelligence for: '{research_query[:60]}...'")
        research_out = browser_agent.search_and_extract(research_query, max_pages=2)
        self.blackboard.set("latest_research", research_out)
        self.blackboard.log("ResearchAgent", "Research synthesis completed.")
        return research_out


class SystemGuardianSubAgent:
    """Specialist sub-agent for telemetry, resource safety, and process diagnostics."""
    def __init__(self, blackboard: HiveBlackboard):
        self.blackboard = blackboard

    def execute(self) -> str:
        self.blackboard.log("GuardianAgent", "Inspecting workstation telemetry and hardware state...")
        status = tools.system_status()
        self.blackboard.set("system_telemetry", status)
        self.blackboard.log("GuardianAgent", "Telemetry check complete.")
        return status


class HiveMindOrchestrator:
    """Central coordinator that decomposes complex user objectives and directs specialist sub-agents."""
    def __init__(self):
        self.blackboard = HiveBlackboard()
        self.coder = CoderSubAgent(self.blackboard)
        self.researcher = ResearcherSubAgent(self.blackboard)
        self.guardian = SystemGuardianSubAgent(self.blackboard)

    def execute_goal(self, goal: str) -> str:
        self.blackboard.log("ExecutiveOrchestrator", f"New multi-agent goal received: '{goal}'")
        goal_lower = goal.lower()

        results = []

        # 1. Hardware & System Safety Check if intensive
        if any(w in goal_lower for w in ("compile", "train", "heavy", "system", "health", "resources")):
            guard_report = self.guardian.execute()
            results.append(f"**System Guardian Telemetry:**\n{guard_report}\n")

        # 2. Research Phase if external knowledge or documentation is needed
        if any(w in goal_lower for w in ("search", "find", "research", "browse", "news", "docs", "documentation", "latest")):
            research_query = goal.replace("research", "").replace("search", "").strip() or goal
            research_report = self.researcher.execute(research_query)
            results.append(f"**Research Agent Intelligence:**\n{research_report}\n")

        # 3. Coding Phase if programming or script creation is required
        if any(w in goal_lower for w in ("code", "script", "python", "build", "create", "write", "develop", "function", "program")):
            context = self.blackboard.get("latest_research", "")
            code_report = self.coder.execute(goal, context=context)
            results.append(f"**Coder Agent Synthesis:**\n{code_report}\n")

        # 4. If general open-ended task, delegate to Coder/Reasoning
        if not results:
            code_report = self.coder.execute(goal)
            results.append(f"**Specialist Output:**\n{code_report}\n")

        # Executive Summary
        executive_summary = [
            "=== [*] Z.A.I.N.E HIVE MIND MULTI-AGENT EXECUTION ===",
            f"Goal: {goal}\n",
            "\n".join(results),
            "=== Agent Collaboration Log ===",
            "\n".join(self.blackboard.logs),
            "\nAll specialist sub-agents have completed execution, Sir."
        ]
        return "\n".join(executive_summary)


def run_hive_mind(goal: str) -> str:
    """Convenience tool entrypoint for Zaine's tool registry."""
    orchestrator = HiveMindOrchestrator()
    return orchestrator.execute_goal(goal)


if __name__ == "__main__":
    test_goal = "Check system health and write a python script in workspace for calculating prime numbers"
    print("Testing Hive Mind with goal:", test_goal)
    out = run_hive_mind(test_goal)
    print("\n--- Output ---")
    print(out)
