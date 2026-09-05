"""
Z.A.I.N.E — YouTube Studio Autonomous 2:00 PM - 5:00 PM Daily Scheduler
Orchestrates automated daily YouTube Shorts generation, publishing, and analytics:
- 14:00 (2:00 PM): AI scriptwriting, Higgsfield AI b-roll, voiceover, and video rendering
- 14:30 (2:30 PM): Resumable video upload with SEO metadata
- 17:00 (5:00 PM): Channel growth stats extraction and executive briefing to Sir
"""

import time
import json
import datetime
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEDULE_STATE_FILE = PROJECT_ROOT / "data" / "youtube_schedule_state.json"


def get_schedule_state() -> Dict[str, Any]:
    """Loads daily schedule checkpoint state."""
    if SCHEDULE_STATE_FILE.exists():
        try:
            with open(SCHEDULE_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_generation_date": "",
        "last_upload_date": "",
        "last_analytics_date": "",
        "latest_video_path": "",
    }


def save_schedule_state(state: Dict[str, Any]):
    """Saves daily schedule checkpoint state."""
    SCHEDULE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULE_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


DAILY_SLOTS = [
    {"id": "slot_1", "hour": 9, "minute": 0, "genre": "facts", "label": "Morning Curiosity (Facts)"},
    {"id": "slot_2", "hour": 12, "minute": 30, "genre": "cat", "label": "Lunchtime Laughs (Cat Memes)"},
    {"id": "slot_3", "hour": 15, "minute": 30, "genre": "gaming", "label": "Afternoon Lore (Gaming)"},
    {"id": "slot_4", "hour": 18, "minute": 30, "genre": "anime", "label": "Prime Battles (Anime)"},
    {"id": "slot_5", "hour": 21, "minute": 30, "genre": "tech", "label": "Late-Night Peak (Tech/Toon)"},
]

MIN_UPLOAD_GAP_SECONDS = 2.5 * 3600  # 2.5 hours anti-spam cooldown between uploads


def check_and_run_daily_youtube_schedule(force: bool = False, topic: str = "", genre: str = "auto") -> Dict[str, Any]:
    """
    Called periodically by heartbeat.py daemon or on-demand by user.
    Manages the 5-Videos-Daily cadence with anti-spam spacing:
    - Slot 1 (09:00): Mind-Blowing Facts
    - Slot 2 (12:30): Funny Cat Memes & Chaos
    - Slot 3 (15:30): Epic Gaming Secrets & Next-Gen Physics
    - Slot 4 (18:30): High-Stakes Anime Battles & Matchups
    - Slot 5 (21:30): Frontier Tech Intelligence / Cartoons
    Enforces minimum 2.5-hour gaps between uploads to protect channel authority.
    """
    now = datetime.datetime.now()
    today_str = now.date().isoformat()
    current_hour = now.hour
    current_minute = now.minute

    state = get_schedule_state()
    actions_taken = []
    dossier_text = ""

    if "completed_slots" not in state or not isinstance(state["completed_slots"], dict):
        state["completed_slots"] = {}
    if today_str not in state["completed_slots"]:
        state["completed_slots"][today_str] = []

    completed_today = state["completed_slots"][today_str]

    # Check anti-spam cooldown
    last_upload_ts = state.get("last_upload_timestamp", 0)
    time_since_last_upload = time.time() - last_upload_ts

    # Determine which slot to run
    active_slot = None
    if force:
        # Pick next uncompleted slot or default to requested genre
        active_slot = next((s for s in DAILY_SLOTS if s["id"] not in completed_today), DAILY_SLOTS[0])
        if genre and genre != "auto":
            active_slot = {"id": f"forced_{genre}", "hour": current_hour, "minute": current_minute, "genre": genre, "label": f"Forced ({genre})"}
    else:
        # Check time-based slots
        for s in DAILY_SLOTS:
            if s["id"] not in completed_today:
                # Is it past this slot's time?
                if current_hour > s["hour"] or (current_hour == s["hour"] and current_minute >= s["minute"]):
                    active_slot = s
                    break

    # If slot is ready and anti-spam cooldown is satisfied (or forced)
    if active_slot:
        if not force and time_since_last_upload < MIN_UPLOAD_GAP_SECONDS:
            remaining_mins = int((MIN_UPLOAD_GAP_SECONDS - time_since_last_upload) / 60)
            actions_taken.append(f"Anti-spam protection active: {remaining_mins}m remaining before next upload window.")
        else:
            slot_genre = active_slot["genre"]
            print(f"\n[YouTube Studio Scheduler] Executing {active_slot['label']} ({slot_genre.upper()})...")
            try:
                import thermal_guard
                thermal_guard.wait_for_thermal_cooldown()

                # 1. Content Generation
                from .content_generator import generate_youtube_short
                short_result = generate_youtube_short(topic=topic, genre=slot_genre, upload_now=True)

                state["last_generation_date"] = today_str
                state["latest_video_path"] = short_result.get("video_path", "")
                state["last_upload_date"] = today_str
                state["last_upload_timestamp"] = time.time()
                if active_slot["id"] not in completed_today:
                    completed_today.append(active_slot["id"])
                state["completed_slots"][today_str] = completed_today
                save_schedule_state(state)

                v_title = short_result.get("title", "")
                dur = short_result.get("duration_sec", 0)
                mb = short_result.get("file_size_mb", 0)
                uploaded_msg = "LIVE on YouTube" if short_result.get("uploaded") else "Queued locally"
                actions_taken.append(f"Published Slot [{active_slot['id'].upper()} - {slot_genre.upper()}]: '{v_title}' ({dur}s, {mb} MB) -> {uploaded_msg}")
            except Exception as e:
                actions_taken.append(f"Slot execution error: {e}")

    # Nightly Analytics Checkpoint (after 22:00)
    if force or (current_hour >= 22 and state.get("last_analytics_date") != today_str):
        print("[YouTube Studio Scheduler] Compiling Nightly YouTube Analytics dossier...")
        try:
            from .analytics import format_analytics_dossier
            dossier_text = format_analytics_dossier()

            # Push to Telegram if configured
            try:
                import telegram_bridge
                telegram_bridge.send_telegram_broadcast(f"📺 **Daily YouTube Studio Report**\n\n{dossier_text}")
            except Exception:
                pass

            # Save to Second Brain Vault
            try:
                import vault
                vault.add_to_vault(
                    title=f"YouTube Channel Growth - {today_str}",
                    content=dossier_text,
                    category="Creator Analytics",
                    tags="youtube,analytics,creator,studio"
                )
            except Exception:
                pass

            state["last_analytics_date"] = today_str
            save_schedule_state(state)
            actions_taken.append("Analytics: Dossier compiled, broadcast, and archived.")
        except Exception as e:
            actions_taken.append(f"Analytics error: {e}")

    in_window = (9 <= current_hour <= 22)
    return {
        "current_time": now.strftime("%H:%M:%S"),
        "in_studio_window": in_window,
        "actions_taken": actions_taken,
        "analytics_dossier": dossier_text,
        "state": state,
    }


def get_studio_status() -> Dict[str, Any]:
    """Returns complete state of the YouTube studio automation pipeline."""
    state = get_schedule_state()
    now = datetime.datetime.now()
    return {
        "active_window": "14:00 - 17:00 (2:00 PM - 5:00 PM)",
        "current_time": now.strftime("%H:%M:%S"),
        "in_active_window": (14 <= now.hour <= 17),
        "last_generation_date": state.get("last_generation_date"),
        "last_upload_date": state.get("last_upload_date"),
        "last_analytics_date": state.get("last_analytics_date"),
        "latest_video_path": state.get("latest_video_path"),
    }
