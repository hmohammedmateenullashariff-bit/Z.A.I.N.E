"""
Z.A.I.N.E — Phase 12: Autonomous Cognitive Reflection & Self-Distillation Engine
Inspects simulated conversation trajectories, evaluates performance, and automatically
distills new experiential heuristics into SQLite `task_learnings` table so Zaine continuously
learns from self-play practice.
"""

import sys
import json
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import memory

DATASET_PATH = PROJECT_ROOT / "data" / "simulated_conversations.jsonl"
DISTILLATION_STATE_PATH = PROJECT_ROOT / "data" / "distillation_checkpoint.json"


def load_distillation_checkpoint() -> int:
    """Returns the line offset of the last analyzed trajectory."""
    if DISTILLATION_STATE_PATH.exists():
        try:
            with open(DISTILLATION_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("last_processed_line", 0)
        except Exception:
            pass
    return 0


def save_distillation_checkpoint(line_number: int):
    """Saves the last processed line number."""
    DISTILLATION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DISTILLATION_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump({"last_processed_line": line_number, "updated_at": datetime.datetime.now().isoformat()}, f)


def extract_heuristic_from_turn(record: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Analyzes a conversation turn and formulates a distilled heuristic for long-term memory.
    """
    prompt = record.get("prompt", "").lower()
    tool = record.get("tool", "")
    response = record.get("response", "")

    # Heuristic Rule 1: Code & Algorithm generation
    if any(k in prompt for k in ["sort", "algorithm", "script", "python", "gcd", "anagram", "matrix"]):
        if tool == "run_python_script" or "write_workspace_file" in response:
            return {
                "domain": "code_execution",
                "lesson": "When implementing algorithms in workspace, write self-contained scripts with test assertions and execute immediately to verify correctness.",
                "keywords": "python script algorithm test workspace assert"
            }
        elif tool == "see_screen":
            return {
                "domain": "tool_selection",
                "lesson": "For pure algorithmic scripting tasks, prefer write_workspace_file and run_python_script directly rather than screen capture.",
                "keywords": "algorithm script run_python_script write_workspace_file"
            }

    # Heuristic Rule 2: Financial & Public APIs
    if any(k in prompt for k in ["weather", "bitcoin", "ethereum", "crypto", "convert", "forex", "usd", "inr"]):
        if tool in ["get_weather", "get_crypto_price", "convert_currency", "query_public_api"]:
            return {
                "domain": "api_integration",
                "lesson": "Real-time pricing and weather queries should leverage zero-key public APIs with concise formatted market summaries.",
                "keywords": "crypto bitcoin weather forex currency rates"
            }

    # Heuristic Rule 3: System Telemetry & Diagnostics
    if any(k in prompt for k in ["system", "cpu", "ram", "battery", "status", "telemetry"]):
        return {
            "domain": "devops_diagnostics",
            "lesson": "Deliver hardware telemetry with exact CPU, RAM, and thermal metrics formatted concisely for Sir.",
            "keywords": "cpu ram thermal battery system status"
        }

    # Heuristic Rule 4: Personal Vault & Memory
    if any(k in prompt for k in ["vault", "remember", "second brain", "note", "recall"]):
        return {
            "domain": "knowledge_management",
            "lesson": "Store notes atomically in the SQLite second brain vault with relevant tags for fast full-text semantic retrieval.",
            "keywords": "vault note second brain recall remember"
        }

    return None


def run_self_distillation_cycle() -> int:
    """
    Reads unanalyzed turns from simulated_conversations.jsonl, extracts heuristics,
    and commits them to zaine_memory.db task_learnings.
    Returns count of newly distilled lessons.
    """
    if not DATASET_PATH.exists():
        return 0

    last_offset = load_distillation_checkpoint()
    new_lessons_count = 0

    try:
        with open(DATASET_PATH, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]

        total_lines = len(lines)
        if total_lines <= last_offset:
            return 0

        for idx in range(last_offset, total_lines):
            try:
                record = json.loads(lines[idx])
                heuristic = extract_heuristic_from_turn(record)
                if heuristic:
                    memory.record_task_learning(
                        task_summary=heuristic["domain"],
                        status="success",
                        lesson_learned=heuristic["lesson"],
                        keywords=heuristic["keywords"]
                    )
                    new_lessons_count += 1
            except Exception as e:
                print(f"[SelfDistillation] Error parsing record {idx}: {e}", file=sys.stderr)

        save_distillation_checkpoint(total_lines)

    except Exception as e:
        print(f"[SelfDistillation] Distillation error: {e}", file=sys.stderr)

    return new_lessons_count


if __name__ == "__main__":
    print("Testing Autonomous Self-Distillation Engine...")
    # Reset checkpoint to 0 for initial test
    save_distillation_checkpoint(0)
    count = run_self_distillation_cycle()
    print(f"Distilled and ingested {count} new experiential lessons from recent simulation turns.")

    # Test retrieval
    test_retrieval = memory.retrieve_relevant_learnings("Can you write a sorting algorithm in python?")
    print(f"\nRetrieved {len(test_retrieval)} relevant lessons for 'sorting algorithm':")
    for l in test_retrieval[:2]:
        print(f" - {l}")
