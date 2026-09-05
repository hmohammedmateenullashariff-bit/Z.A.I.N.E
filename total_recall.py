"""
Z.A.I.N.E — Phase 10: Omnipresent Temporal Context & Audio-Visual Memory ("Total Recall")
Maintains an in-RAM circular timeline ring buffer and persistent journal of events,
enabling chronological time-travel queries ("What did we do 15 minutes ago?",
"What was the result of the last script run?", "What was on my screen?").
"""

import sys
import json
import time
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
JOURNAL_PATH = PROJECT_ROOT / "data" / "temporal_journal.jsonl"
MAX_RING_SIZE = 250  # Keep last 250 temporal events in memory


class TemporalRingBuffer:
    """In-memory circular event buffer with persistence to temporal_journal.jsonl."""
    def __init__(self, capacity: int = MAX_RING_SIZE):
        self.capacity = capacity
        self.events: List[Dict[str, Any]] = []
        self._load_recent()

    def _load_recent(self):
        """Loads the most recent events from disk on startup."""
        if JOURNAL_PATH.exists():
            try:
                with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f if l.strip()]
                # Load last N lines
                for line in lines[-self.capacity:]:
                    try:
                        self.events.append(json.loads(line))
                    except Exception:
                        pass
            except Exception as e:
                print(f"[TotalRecall] Warning loading journal: {e}", file=sys.stderr)

    def record_event(self, event_type: str, summary: str, details: Optional[Dict[str, Any]] = None):
        """Records a new timestamped temporal event."""
        now = datetime.datetime.now()
        entry = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "epoch": time.time(),
            "type": event_type,  # e.g., 'conversation', 'tool_exec', 'file_edit', 'system_event', 'screen'
            "summary": summary,
            "details": details or {}
        }
        self.events.append(entry)
        if len(self.events) > self.capacity:
            self.events.pop(0)

        # Append to disk journal
        try:
            JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[TotalRecall] Failed to persist event: {e}", file=sys.stderr)

    def query(self, query: str = "", lookback_minutes: int = 60, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves matching events from the temporal buffer within the lookback window.
        """
        cutoff_epoch = time.time() - (lookback_minutes * 60)
        matches = []
        q_lower = query.lower() if query else ""

        for ev in reversed(self.events):
            if ev.get("epoch", 0) < cutoff_epoch:
                continue
            if event_type and ev.get("type") != event_type:
                continue
            if q_lower:
                combined_text = (ev.get("summary", "") + " " + json.dumps(ev.get("details", ""))).lower()
                if q_lower not in combined_text:
                    continue
            matches.append(ev)

        return matches

    def format_timeline(self, lookback_minutes: int = 30) -> str:
        """Formats an executive timeline of recent activities for Zaine."""
        events = self.query(lookback_minutes=lookback_minutes)
        if not events:
            return f"No significant events recorded in the last {lookback_minutes} minutes, Sir."

        lines = [
            f"=== TEMPORAL ACTIVITY TIMELINE (Last {lookback_minutes} Minutes) ==="
        ]
        for ev in reversed(events):
            time_str = ev.get("timestamp", "").split()[-1]
            etype = ev.get("type", "EVENT").upper()
            summary = ev.get("summary", "")
            lines.append(f"[{time_str}] [{etype}] {summary}")
        lines.append("==================================================")
        return "\n".join(lines)


# Global singleton instance
recall_buffer = TemporalRingBuffer()


def record_temporal_event(event_type: str, summary: str, details: Optional[Dict[str, Any]] = None):
    recall_buffer.record_event(event_type, summary, details)


def recall_recent_activity(query: str = "", lookback_minutes: int = 30) -> str:
    """Public helper for Zaine to query what happened recently."""
    if not query:
        return recall_buffer.format_timeline(lookback_minutes=lookback_minutes)

    matches = recall_buffer.query(query=query, lookback_minutes=lookback_minutes)
    if not matches:
        return f"I found no records matching '{query}' in the last {lookback_minutes} minutes, Sir."

    lines = [f"Found {len(matches)} temporal events matching '{query}':"]
    for m in matches:
        lines.append(f"- [{m.get('timestamp')}] ({m.get('type')}) {m.get('summary')}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("Testing Total Recall Temporal Context Engine...")
    record_temporal_event("file_edit", "Created quick_sort.py in workspace", {"file": "quick_sort.py"})
    record_temporal_event("tool_exec", "Executed run_python_script on quick_sort.py successfully", {"exit_code": 0})
    record_temporal_event("conversation", "User requested live weather forecast for London", {"city": "London"})

    timeline = recall_recent_activity(lookback_minutes=10)
    print("\nFormatted Timeline:")
    print(timeline)

    search_res = recall_recent_activity(query="quick_sort", lookback_minutes=10)
    print("\nSearch Result:")
    print(search_res)
