"""
Z.A.I.N.E — YouTube Studio Autonomous 2:00 PM - 5:00 PM Daily Scheduler
Orchestrates automated daily YouTube Shorts generation, publishing, and analytics:
- 14:00 (2:00 PM): AI scriptwriting, Higgsfield AI b-roll, voiceover, and video rendering
- 14:30 (2:30 PM): Resumable video upload with SEO metadata
- 17:00 (5:00 PM): Channel growth stats extraction and executive briefing to Sir
"""

import os
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


def check_and_run_daily_youtube_schedule(force: bool = False, topic: str = "") -> Dict[str, Any]:
    """
    Called periodically by heartbeat.py daemon or on-demand by user.
    Checks if current local time is within the 14:00 - 17:00 (2-5 PM) window
    (or force=True) and triggers daily studio milestones:
    1. Content Generation (Short video)
    2. YouTube Upload / Queueing
    3. Channel Analytics Dossier
    """
    now = datetime.datetime.now()
    today_str = now.date().isoformat()
    current_hour = now.hour
    current_minute = now.minute

    state = get_schedule_state()
    actions_taken = []
    dossier_text = ""

    in_window = (14 <= current_hour <= 17)

    if in_window or force:
        # 1. Milestone 1: Content Generation
        if force or (current_hour >= 14 and state.get("last_generation_date") != today_str):
            print("\n[YouTube Studio Scheduler] Milestone 1 Triggered: Initiating AI Short generation...")
            try:
                import thermal_guard
                thermal_guard.wait_for_thermal_cooldown()

                from .content_generator import generate_youtube_short
                short_result = generate_youtube_short(topic=topic)

                state["last_generation_date"] = today_str
                state["latest_video_path"] = short_result.get("video_path", "")
                save_schedule_state(state)
                actions_taken.append(f"Rendered Short: '{short_result.get('title')}' ({short_result.get('duration_sec')}s, {short_result.get('file_size_mb')} MB)")
            except Exception as e:
                actions_taken.append(f"Generation error: {e}")

        # 2. Milestone 2: Video Upload / Queue
        if force or ((current_hour > 14 or (current_hour == 14 and current_minute >= 30)) and state.get("last_upload_date") != today_str):
            video_path = state.get("latest_video_path")
            if video_path and os.path.exists(video_path):
                print("[YouTube Studio Scheduler] Milestone 2 Triggered: Uploading Short to channel...")
                try:
                    from .uploader import upload_youtube_video
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
                    status_msg = up_result.get("message") or up_result.get("status")
                    actions_taken.append(f"Upload: {status_msg}")
                except Exception as e:
                    actions_taken.append(f"Upload error: {e}")

        # 3. Milestone 3: Channel Analytics & Briefing
        if force or (current_hour >= 17 and state.get("last_analytics_date") != today_str):
            print("[YouTube Studio Scheduler] Milestone 3 Triggered: Compiling YouTube Analytics dossier...")
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
                actions_taken.append("Delivered YouTube Analytics debrief")
            except Exception as e:
                actions_taken.append(f"Analytics error: {e}")

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
