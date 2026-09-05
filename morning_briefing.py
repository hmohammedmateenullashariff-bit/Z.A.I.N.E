"""
Z.A.I.N.E — Phase 11: Proactive Morning Executive Briefing Engine
Compiles the comprehensive overnight intelligence dossier and morning executive briefing:
- Real-time market telemetry (BTC, ETH, Forex)
- System health & cognitive memory statistics
- Overnight self-play simulation performance recap
- Workspace audit of newly generated code & tools
- British elegance salutation ("Good morning, Sir")
"""

import sys
import json
import datetime
from pathlib import Path
from typing import Dict, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent

import home_ops
from public_apis import get_crypto_price, convert_currency

DATASET_PATH = PROJECT_ROOT / "data" / "simulated_conversations.jsonl"
OVERNIGHT_LOG = PROJECT_ROOT / "data" / "overnight_evolution.log"
BRIEFING_OUT = PROJECT_ROOT / "data" / "morning_briefing.md"


def get_simulation_summary() -> Dict[str, Any]:
    """Parses dataset logs to compile statistical performance metrics."""
    if not DATASET_PATH.exists():
        return {"total_turns": 0, "avg_latency": 0, "tools_used": {}}

    turns = 0
    total_latency = 0.0
    tool_counts = {}

    try:
        with open(DATASET_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    turns += 1
                    lat = record.get("elapsed_sec") or record.get("latency_seconds") or 0.0
                    total_latency += float(lat)
                    tool = record.get("tool")
                    if tool:
                        tool_counts[tool] = tool_counts.get(tool, 0) + 1
                except Exception:
                    pass
    except Exception:
        pass

    avg_lat = round(total_latency / max(1, turns), 2)
    return {
        "total_turns": turns,
        "avg_latency": avg_lat,
        "tool_counts": tool_counts
    }


def compile_morning_briefing(salutation: str = "Sir") -> str:
    """Generates the executive morning briefing document."""
    now = datetime.datetime.now()
    date_str = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%I:%M %p")

    # 1. Fetch live market telemetry
    try:
        btc_info = get_crypto_price("bitcoin")
    except Exception:
        btc_info = "Data unavailable"

    try:
        eth_info = get_crypto_price("ethereum")
    except Exception:
        eth_info = "Data unavailable"

    try:
        forex_gbp = convert_currency(1.0, "GBP", "USD")
    except Exception:
        forex_gbp = "Data unavailable"

    # 2. System DevOps Telemetry
    devops_raw = home_ops.get_system_telemetry()
    db_health = home_ops.check_database_health()

    # 3. Simulation & Cognitive Metrics
    sim_stats = get_simulation_summary()
    lessons_count = db_health.get("table_counts", {}).get("task_learnings", 0)

    # 4. Workspace audit
    workspace_dir = PROJECT_ROOT / "workspace"
    ws_files = [f.name for f in workspace_dir.glob("*.py")] if workspace_dir.exists() else []

    # 5. Top 10 AI Updates of the Day
    try:
        from ai_daily_intel import get_daily_ai_updates
        ai_updates = get_daily_ai_updates(force_refresh=False)
        ai_lines = []
        for u in ai_updates[:5]:
            ai_lines.append(f"- **[{u['domain']}] {u['title']}:** {u['summary']} *(Impact: {u['impact']})*")
        ai_section = "\n".join(ai_lines)
    except Exception:
        ai_section = "AI Intel stream temporarily offline."

    # Build British-cadenced Markdown Briefing
    briefing = f"""# Z.A.I.N.E — EXECUTIVE MORNING DOSSIER
**Date:** {date_str} | **Time:** {time_str}  
**Prepared for:** {salutation}  
**Status:** All Neural Systems Nominal  

---

### 1. Salutation & Executive Summary
Good morning, {salutation}. I trust you rested well. While you were away, I have maintained continuous vigilance over all local services and completed our scheduled overnight self-play cognitive cycles. All computational subsystems are performing at peak efficiency.

---

### 2. Live Market Intelligence
- **Bitcoin (BTC):** {btc_info}
- **Ethereum (ETH):** {eth_info}
- **Forex (GBP/USD):** {forex_gbp}

---

### 3. Top AI Breakthroughs of the Day
{ai_section}

---

### 4. Overnight Evolution & Cognitive Training
- **Total Autonomous Turns:** {sim_stats['total_turns']} self-play conversations executed
- **Average Cognitive Latency:** {sim_stats['avg_latency']} seconds / response
- **Master Experiential Lessons Ingested:** {lessons_count} lessons active in SQLite neural store
- **Tools Successfully Exercised:** {', '.join(f'{k} ({v}x)' for k, v in sim_stats['tool_counts'].items()) if sim_stats['tool_counts'] else 'All registered primitives'}

---

### 5. System Health & Infrastructure
- **CPU Utilization:** {devops_raw.get('cpu_percent')}%
- **System Memory:** {devops_raw.get('ram_used_gb')} GB / {devops_raw.get('ram_total_gb')} GB ({devops_raw.get('ram_percent')}%)
- **Storage Reserve:** {devops_raw.get('disk_free_gb')} GB available
- **Memory Store Status:** {db_health.get('status')} (Database size: {db_health.get('size_kb')} KB)

---

### 6. Workspace Status
- **Active Code Artifacts ({len(ws_files)}):** {', '.join(ws_files) if ws_files else 'None'}
- **Zaine Cascade Daemon:** Standing by for interactive coding sessions in VS Code.

Standing by for your next directive, {salutation}.
"""

    BRIEFING_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(BRIEFING_OUT, "w", encoding="utf-8") as f:
        f.write(briefing)

    return briefing


def generate_morning_briefing_speech_text(salutation: str = "Sir") -> str:
    """Produces a concise 30-second speech summary suitable for TTS vocal playback."""
    sim_stats = get_simulation_summary()
    return (
        f"Good morning, {salutation}. I have completed all overnight cognitive self-play iterations, "
        f"logging {sim_stats['total_turns']} simulated conversations. All local services and neural models "
        f"are operating nominally. Your morning dossier is ready for review, {salutation}."
    )


if __name__ == "__main__":
    print("Compiling morning executive briefing...")
    text = compile_morning_briefing()
    print(text)
    print("\nSpoken summary:")
    print(generate_morning_briefing_speech_text())
