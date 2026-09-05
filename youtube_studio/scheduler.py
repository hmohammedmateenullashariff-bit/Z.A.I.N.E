"""
Z.A.I.N.E — YouTube Studio Autonomous 2:00 PM - 5:00 PM Daily Scheduler
Orchestrates automated daily YouTube Shorts generation, publishing, and analytics:
- 14:00 (2:00 PM): AI scriptwriting, Higgsfield AI b-roll, voiceover, and video rendering
- 14:30 (2:30 PM): Resumable video upload with SEO metadata
- 17:00 (5:00 PM): Channel growth stats extraction and executive briefing to Sir
"""

import os
import sys
import json
import time
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


def check_and_run_daily_youtube_schedule() -> Dict[str, Any]:
    """
    Called periodically by heartbeat.py daemon.
    Checks if current local time is within the 14:00 - 17:00 (2-5 PM) window
    and triggers appropriate daily studio milestones.
    """
    now = datetime.datetime.now()
    today_str = now.date().isoformat()
    current_hour = now.hour
    current_minute = now.minute

    state = get_schedule_state()
    actions_taken = []

    # Window Check: 14:00 to 17:59 (2:00 PM to 5:59 PM)
    if 14 <= current_hour <= 17:
        # 1. Milestone 1: 14:00 (2:00 PM) — Content Generation
        if current_hour >= 14 and state.get("last_generation_date") != today_str:
            print(f"\n[YouTube Studio Scheduler] 14:00 Milestone Triggered. Initiating AI Short generation...")
            try:
                # Check thermal safety before rendering
                import thermal_guard
                thermal_guard.wait_for_thermal_cooldown()

                from .content_generator import generate_youtube_short
                short_result = generate_youtube_short()

                state["last_generation_date"] = today_str
                state["latest_video_path"] = short_result.get("video_path", "")
                save_schedule_state(state)
                actions_taken.append(f"Rendered new Short: '{short_result.get('title')}'")
            except Exception as e:
                actions_taken.append(f"Generation error: {e}")

        # 2. Milestone 2: 14:30 (2:30 PM) — Video Upload
        if (current_hour > 14 or (current_hour == 14 and current_minute >= 30)) and state.get("last_upload_date") != today_str:
            video_path = state.get("latest_video_path")
            if video_path and os.path.exists(video_path):
                print(f"[YouTube Studio Scheduler] 14:30 Milestone Triggered. Uploading Short to channel...")
                try:
                    from .uploader import upload_youtube_video
                    # Load companion metadata JSON if present
                    json_path = video_path.replace(".mp4", ".json")
                    title = "Daily AI Breakthrough #Shorts"
                    description = ""
                    tags = ["Shorts", "AI", "Technology"]
                    if os.path.exists(json_path):
                        with open(json_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            title = meta.get("title", title)
                            description = meta.get("description", description)
                            tags = meta.get("tags", tags)

                    up_result = upload_youtube_video(video_path, title=title, description=description, tags=tags)
                    state["last_upload_date"] = today_str
                    save_schedule_state(state)
                    actions_taken.append(f"Upload status: {up_result.get('status')}")
                except Exception as e:
                    actions_taken.append(f"Upload error: {e}")

        # 3. Milestone 3: 17:00 (5:00 PM) — Channel Analytics & Briefing
        if current_hour >= 17 and state.get("last_analytics_date") != today_str:
            print(f"[YouTube Studio Scheduler] 17:00 Milestone Triggered. Compiling YouTube Analytics dossier...")
            try:
                from .analytics import format_analytics_dossier
                dossier = format_analytics_dossier()

                # Push to Telegram if configured
                try:
                    import telegram_bridge
                    telegram_bridge.send_telegram_broadcast(f"📺 **Daily YouTube Studio Report (5:00 PM)**\n\n{dossier}")
                except Exception:
                    pass

                # Save to Second Brain Vault
                try:
                    import vault
                    vault.add_to_vault(
                        title=f"YouTube Channel Growth - {today_str}",
                        content=dossier,
                        category="Creator Analytics",
                        tags="youtube,analytics,creator,studio"
                    )
                except Exception:
                    pass

                state["last_analytics_date"] = today_str
                save_schedule_state(state)
                actions_taken.append("Delivered 5:00 PM YouTube Analytics debrief")
            except Exception as e:
                actions_taken.append(f"Analytics error: {e}")

    return {
        "current_time": now.strftime("%H:%M:%S"),
        "in_studio_window": (14 <= current_hour <= 17),
        "actions_taken": actions_taken,
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
