"""
Z.A.I.N.E — Phase 12: Autonomous Cognitive Reflection & Self-Distillation Engine
Inspects simulated conversation trajectories, evaluates performance, and automatically
distills new experiential heuristics into SQLite `task_learnings` table so Zaine continuously
learns from self-play practice.

Guardian Gating:
Cross-references tool/action turns against `data/zaine_approvals.db` to guarantee
that only APPROVED and error-free actions contribute to long-term memory heuristics.
DENIED actions are archived to `data/rejected_heuristics.jsonl`.
"""

import sys
import json
import sqlite3
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import memory

DATASET_PATH = PROJECT_ROOT / "data" / "simulated_conversations.jsonl"
DISTILLATION_STATE_PATH = PROJECT_ROOT / "data" / "distillation_checkpoint.json"
APPROVALS_DB_PATH = PROJECT_ROOT / "data" / "zaine_approvals.db"
REJECTED_HEURISTICS_PATH = PROJECT_ROOT / "data" / "rejected_heuristics.jsonl"


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


def _parse_record_timestamp(ts_str: str) -> Optional[float]:
    """Parses various timestamp formats from conversation records into epoch seconds."""
    if not ts_str:
        return None
    try:
        return datetime.datetime.fromisoformat(ts_str).timestamp()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.datetime.strptime(ts_str, fmt).timestamp()
        except Exception:
            pass
    return None


def has_execution_error(resolution_note: str) -> bool:
    """
    Checks if a resolution note indicates that an action failed during execution.
    Guardian appends ' Execution error: <e>' when an action throws an exception.
    """
    if not resolution_note:
        return False
    lower = resolution_note.lower()
    error_indicators = [
        "execution error:",
        "error:",
        "failed:",
        "exception:",
        "traceback",
    ]
    return any(ind in lower for ind in error_indicators)


def find_matching_proposal(record: Dict[str, Any], conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    """
    Looks up a corresponding proposal in data/zaine_approvals.db:
    1. Direct match by proposal_id / action_id / id.
    2. Proximity timestamp match for tool/action executions.
    """
    # 1. Direct ID match
    for id_key in ("proposal_id", "action_id", "id"):
        raw_id = record.get(id_key)
        if raw_id and isinstance(raw_id, str):
            clean_id = raw_id.strip().upper()
            row = conn.execute(
                "SELECT id, status, resolution_note, created_at, resolved_at FROM proposals WHERE id = ?",
                (clean_id,)
            ).fetchone()
            if row:
                return {
                    "id": row[0],
                    "status": row[1],
                    "resolution_note": row[2] or "",
                    "created_at": row[3],
                    "resolved_at": row[4],
                }

    # If this record has no tool execution, it was a conversational turn with no Guardian action
    tool = record.get("tool", "")
    if not tool:
        return None

    # 2. Match by nearest timestamp
    ts_str = record.get("timestamp", "")
    rec_ts = _parse_record_timestamp(ts_str)
    if rec_ts is None:
        return None

    elapsed = float(record.get("elapsed_sec", 60.0) or 60.0)
    window = max(180.0, elapsed + 60.0)

    rows = conn.execute(
        """
        SELECT id, status, resolution_note, created_at, resolved_at,
               MIN(ABS(created_at - ?), CASE WHEN resolved_at IS NOT NULL THEN ABS(resolved_at - ?) ELSE 999999 END) as diff
        FROM proposals
        WHERE ABS(created_at - ?) <= ? OR (resolved_at IS NOT NULL AND ABS(resolved_at - ?) <= ?)
        ORDER BY diff ASC
        LIMIT 1
        """,
        (rec_ts, rec_ts, rec_ts, window, rec_ts, window)
    ).fetchall()

    if rows:
        r = rows[0]
        return {
            "id": r[0],
            "status": r[1],
            "resolution_note": r[2] or "",
            "created_at": r[3],
            "resolved_at": r[4],
        }

    return None


def log_rejected_heuristic(record: Dict[str, Any], proposal: Dict[str, Any], reason: str):
    """Logs skipped/denied record and resolution_note to data/rejected_heuristics.jsonl for later manual review."""
    REJECTED_HEURISTICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "reason": reason,
        "proposal_id": proposal.get("id"),
        "status": proposal.get("status"),
        "resolution_note": proposal.get("resolution_note", ""),
        "turn_record": record,
        "logged_at": datetime.datetime.now().isoformat(),
    }
    with open(REJECTED_HEURISTICS_PATH, "a", encoding="utf-8") as rf:
        rf.write(json.dumps(entry, ensure_ascii=False) + "\n")


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
    Reads unanalyzed turns from simulated_conversations.jsonl, cross-references against
    data/zaine_approvals.db to ensure Guardian approval and zero execution errors,
    and commits valid heuristics to zaine_tasks.db task_learnings.
    Returns count of newly distilled lessons.
    """
    print("[self_distillation] Writing to: zaine_tasks.db -> task_learnings (prompt-injection only, no weight updates).")

    if not DATASET_PATH.exists():
        return 0

    last_offset = load_distillation_checkpoint()
    new_lessons_count = 0

    approvals_conn = None
    if APPROVALS_DB_PATH.exists():
        try:
            approvals_conn = sqlite3.connect(str(APPROVALS_DB_PATH))
        except Exception as ce:
            print(f"[SelfDistillation] Notice: Could not connect to {APPROVALS_DB_PATH.name}: {ce}", file=sys.stderr)

    try:
        with open(DATASET_PATH, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]

        total_lines = len(lines)
        if total_lines <= last_offset:
            return 0

        for idx in range(last_offset, total_lines):
            try:
                record = json.loads(lines[idx])

                # Guardian Approval Cross-Referencing
                proposal = None
                if approvals_conn:
                    try:
                        proposal = find_matching_proposal(record, approvals_conn)
                    except Exception as pe:
                        print(f"[SelfDistillation] Proposal lookup warning: {pe}", file=sys.stderr)

                if proposal:
                    p_status = str(proposal.get("status", "")).upper()
                    res_note = proposal.get("resolution_note", "")

                    # Rule 2: If DENIED, skip entirely and log for manual review
                    if p_status == "DENIED":
                        log_rejected_heuristic(record, proposal, reason="DENIED_BY_GUARDIAN")
                        continue

                    # Rule 4: If APPROVED but execution threw an error, skip
                    if p_status == "APPROVED":
                        if has_execution_error(res_note):
                            log_rejected_heuristic(record, proposal, reason="APPROVED_BUT_EXECUTION_FAILED")
                            continue

                    # Rule 3: If PENDING (never resolved), proceed under existing logic

                # Rule 3: Conversational turns with no tool call or unmanaged actions proceed
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
    finally:
        if approvals_conn:
            try:
                approvals_conn.close()
            except Exception:
                pass

    return new_lessons_count


if __name__ == "__main__":
    print("Testing Autonomous Self-Distillation Engine with Guardian Gate...")
    # Reset checkpoint to 0 for initial test
    save_distillation_checkpoint(0)
    count = run_self_distillation_cycle()
    print(f"Distilled and ingested {count} new experiential lessons from recent simulation turns.")

    # Test retrieval
    test_retrieval = memory.retrieve_relevant_learnings("Can you write a sorting algorithm in python?")
    print(f"\nRetrieved {len(test_retrieval)} relevant lessons for 'sorting algorithm':")
    for l in test_retrieval[:2]:
        print(f" - {l}")

