"""
Z.A.I.N.E — YouTube Studio Autonomous 2:00 PM - 5:00 PM Daily Scheduler
Orchestrates automated daily YouTube Shorts generation, publishing, and analytics:
- 14:00 (2:00 PM): AI scriptwriting, Higgsfield AI b-roll, voiceover, and video rendering
- 14:30 (2:30 PM): Resumable video upload with SEO metadata
- 17:00 (5:00 PM): Channel growth stats extraction and executive briefing to Sir
"""

import os
import sys
import time
import json
import uuid
import shutil
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEDULE_STATE_FILE = PROJECT_ROOT / "data" / "youtube_schedule_state.json"
PENDING_REVIEW_DIR = PROJECT_ROOT / "data" / "pending_review"
REJECTED_DIR = PROJECT_ROOT / "youtube_studio" / "rejected"

PENDING_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
REJECTED_DIR.mkdir(parents=True, exist_ok=True)


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


# Overnight Quiet Hours (22:00 - 08:30) — Strictly silences automated notifications and overnight renders
NIGHT_QUIET_START = 22  # 10:00 PM
NIGHT_QUIET_END = 8     # 8:00 AM (ends at 08:30)

# Daytime Non-Spam Slots (08:30 - 21:30) — Balanced rotation across genres during waking hours only
DAILY_SLOTS = [
    {"id": "slot_01_morning_tech", "hour": 8, "minute": 30, "genre": "tech", "label": "Slot 1 (08:30) — Morning AI & Tech Frontier Intel"},
    {"id": "slot_02_mid_morning_facts", "hour": 11, "minute": 0, "genre": "facts", "label": "Slot 2 (11:00) — Mind-Blowing Science & Secrets"},
    {"id": "slot_03_midday_gaming", "hour": 13, "minute": 30, "genre": "gaming", "label": "Slot 3 (13:30) — Midday Gaming Physics & Secrets"},
    {"id": "slot_04_afternoon_anime", "hour": 16, "minute": 0, "genre": "anime", "label": "Slot 4 (16:00) — Afternoon Anime Combat (Diversified Roster)"},
    {"id": "slot_05_evening_animation", "hour": 18, "minute": 30, "genre": "animated", "label": "Slot 5 (18:30) — Whimsical Animation & Storytelling"},
    {"id": "slot_06_prime_anime", "hour": 21, "minute": 0, "genre": "anime", "label": "Slot 6 (21:00) — Prime Anime Battle Climax (Novel Soundtrack)"},
]

MIN_UPLOAD_GAP_SECONDS = 2.5 * 3600  # 2.5 hours minimum spacing between uploads


def get_pending_reviews() -> List[Dict[str, Any]]:
    """Loads all pending video review items sorted by creation time."""
    PENDING_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for p in PENDING_REVIEW_DIR.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                items.append(json.load(f))
        except Exception:
            pass
    items.sort(key=lambda x: x.get("created_timestamp", 0))
    return items


def get_pending_review_item(proposal_id: str) -> Optional[Dict[str, Any]]:
    """Fetches a specific pending review item by proposal ID."""
    clean_id = proposal_id.strip()
    json_path = PENDING_REVIEW_DIR / f"{clean_id}.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_pending_review_item(item: Dict[str, Any]):
    """Saves a pending review item descriptor to data/pending_review/."""
    PENDING_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pid = item.get("proposal_id", f"YT-{uuid.uuid4().hex[:4].upper()}")
    json_path = PENDING_REVIEW_DIR / f"{pid}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(item, f, indent=2)


def is_slot_pending(slot_id: str) -> bool:
    """Checks if a cadence slot is already rendered and waiting for human approval."""
    for item in get_pending_reviews():
        if item.get("slot_id") == slot_id and item.get("status") == "PENDING_REVIEW":
            return True
    return False


def mark_slot_completed(slot_id: str, video_path: str = ""):
    """Marks a cadence slot as completed in state once approved and uploaded."""
    state = get_schedule_state()
    today_str = datetime.datetime.now().date().isoformat()
    if "completed_slots" not in state or not isinstance(state["completed_slots"], dict):
        state["completed_slots"] = {}
    if today_str not in state["completed_slots"]:
        state["completed_slots"][today_str] = []

    if slot_id and slot_id not in state["completed_slots"][today_str]:
        state["completed_slots"][today_str].append(slot_id)

    state["last_upload_date"] = today_str
    state["last_upload_timestamp"] = time.time()
    if video_path:
        state["latest_video_path"] = video_path
    save_schedule_state(state)


def kill_render_process_for_slot(video_path: str = "", slot_id: str = "", proposal_id: str = "") -> None:
    """Terminates any active ffmpeg process rendering this slot or target video path."""
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info.get('name') or ''
                if 'ffmpeg' in name.lower():
                    cmdline_list = proc.info.get('cmdline') or []
                    cmdline = ' '.join(cmdline_list)
                    match = False
                    if video_path and os.path.basename(video_path) in cmdline:
                        match = True
                    if slot_id and slot_id in cmdline:
                        match = True
                    if proposal_id and proposal_id in cmdline:
                        match = True
                    if match:
                        print(f"[YouTube Studio] Killing active FFmpeg process PID {proc.info['pid']} for rejected {slot_id or video_path}")
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        print(f"[YouTube Studio] Process inspection note: {e}")


def is_slot_rejected_cooldown(state: Dict[str, Any], today_str: str, slot_id: str, cooldown_hours: float = 4.0) -> bool:
    """Checks if a slot was rejected today and is still within the cooldown window (default 4 hours)."""
    rejected_today = state.get("rejected_today", {})
    if isinstance(rejected_today, dict) and today_str in rejected_today:
        day_rejections = rejected_today[today_str]
        if isinstance(day_rejections, dict) and slot_id in day_rejections:
            rej_ts = day_rejections[slot_id]
            if isinstance(rej_ts, (int, float)):
                if time.time() - rej_ts < cooldown_hours * 3600:
                    return True
        elif isinstance(day_rejections, list) and slot_id in day_rejections:
            return True
    return False


def reject_pending_video(proposal_id: str) -> Dict[str, Any]:
    """
    Called when Sir taps [ ❌ REJECT & SKIP ] via Telegram.
    On REJECT:
    1. Terminates any active FFmpeg render subprocess for this slot/video.
    2. Immediately hard-deletes the rendered video file to preserve disk space.
    3. Records the rejection with a 4-hour cooldown in state to prevent infinite reject-render loops.
    4. Removes item from pending review queue.
    """
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    item = get_pending_review_item(proposal_id)
    if not item:
        return {"status": "ERROR", "error": f"Proposal '{proposal_id}' not found in queue."}

    video_path = item.get("video_path", "")
    title = item.get("title", "YouTube Short")
    slot_id = item.get("slot_id", "")

    # Kill any active FFmpeg subprocess rendering for this slot before deleting
    kill_render_process_for_slot(video_path=video_path, slot_id=slot_id, proposal_id=proposal_id)

    # Immediately delete rejected video file to preserve disk space
    if video_path and os.path.exists(video_path):
        try:
            os.remove(video_path)
            print(f"[YouTube Studio] Deleted rejected video file: {video_path}")
        except Exception as me:
            print(f"[YouTube Studio Error removing rejected file]: {me}")

    # Track rejected slot today with 4-hour cooldown and free slot from completed
    if slot_id:
        state = get_schedule_state()
        today_str = datetime.datetime.now().date().isoformat()
        now_ts = time.time()
        if "rejected_today" not in state or not isinstance(state["rejected_today"], dict):
            state["rejected_today"] = {}
        if today_str not in state["rejected_today"] or not isinstance(state["rejected_today"][today_str], dict):
            state["rejected_today"][today_str] = {}
        state["rejected_today"][today_str][slot_id] = now_ts

        if "completed_slots" in state and isinstance(state["completed_slots"], dict):
            if today_str in state["completed_slots"]:
                if slot_id in state["completed_slots"][today_str]:
                    state["completed_slots"][today_str].remove(slot_id)
        save_schedule_state(state)
        print(f"[YouTube Studio] Slot '{slot_id}' marked as rejected with 4-hour cooldown.")

    # Mark rejected in approval registry if present
    try:
        from approval import ApprovalRegistry
        ApprovalRegistry.deny(proposal_id, note="Rejected via Telegram by Sir")
    except Exception:
        pass

    # Remove review queue json
    json_path = PENDING_REVIEW_DIR / f"{proposal_id}.json"
    if json_path.exists():
        try:
            json_path.unlink()
        except Exception:
            pass

    return {
        "status": "REJECTED",
        "title": title,
        "proposal_id": proposal_id,
        "slot_id": slot_id,
    }


def prune_stale_studio_media(max_age_hours: float = 24.0) -> Dict[str, Any]:
    """
    Automatically purges old and transient studio media to eliminate folder bloat:
    - Cleans youtube_studio/rejected/ entirely.
    - Deletes old voiceover .wav files in youtube_shorts/ older than 6 hours.
    - Purges temporary clips in scratch/ older than 12 hours.
    - Deletes obsolete master video renders in workspace/videos/ and workspace/youtube_shorts/
      that are not currently awaiting review.
    - Cleans up duplicate uncompressed .wav audio files when compressed streams exist.
    """
    now_ts = time.time()
    cleaned_count = 0
    freed_bytes = 0

    # 1. Clean rejected folder
    if REJECTED_DIR.exists():
        for rf in REJECTED_DIR.glob("*"):
            if rf.is_file():
                try:
                    sz = rf.stat().st_size
                    rf.unlink()
                    cleaned_count += 1
                    freed_bytes += sz
                except Exception:
                    pass

    # 2. Clean old voiceovers
    shorts_dir = PROJECT_ROOT / "workspace" / "youtube_shorts"
    if shorts_dir.exists():
        for wav in shorts_dir.glob("voiceover_*.wav"):
            try:
                if now_ts - wav.stat().st_mtime > 6 * 3600:
                    sz = wav.stat().st_size
                    wav.unlink()
                    cleaned_count += 1
                    freed_bytes += sz
            except Exception:
                pass

    # 3. Clean stale scratch clips in scratch/
    scratch_dir = PROJECT_ROOT / "scratch"
    if scratch_dir.exists():
        for f in scratch_dir.glob("**/*"):
            if f.is_file() and f.suffix.lower() in (".mp4", ".wav", ".webm"):
                try:
                    if now_ts - f.stat().st_mtime > 12 * 3600:
                        sz = f.stat().st_size
                        f.unlink()
                        cleaned_count += 1
                        freed_bytes += sz
                except Exception:
                    pass

    # 4. Clean duplicate uncompressed .wav audio in workspace/audio/bg_music/
    bg_music_dir = PROJECT_ROOT / "workspace" / "audio" / "bg_music"
    if bg_music_dir.exists():
        for wav in bg_music_dir.glob("*.wav"):
            try:
                # If an m4a or webm with the same stem exists, remove the heavy uncompressed wav
                stem = wav.stem
                if (bg_music_dir / f"{stem}.m4a").exists() or (bg_music_dir / f"{stem}.webm").exists():
                    sz = wav.stat().st_size
                    wav.unlink()
                    cleaned_count += 1
                    freed_bytes += sz
            except Exception:
                pass

    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    return {"cleaned_count": cleaned_count, "freed_mb": freed_mb}


def check_pending_reviews() -> List[str]:
    """
    Enforces the human-in-the-loop SLA:
    - Overnight Quiet Hours (22:00 - 08:30) strictly silence all reminders and retries.
    - If no response within 2 hours, video remains in data/pending_review/ (no auto-publish/discard).
    - Sends reminder ping at 3-hour mark.
    - Sends final alert ping at 6-hour mark.
    - Video retry dispatch capped at 3 retries with exponential backoff (15s, 60s, 300s).
    """
    cur_dt = datetime.datetime.now()
    is_quiet_hours = cur_dt.hour >= NIGHT_QUIET_START or cur_dt.hour < NIGHT_QUIET_END or (cur_dt.hour == NIGHT_QUIET_END and cur_dt.minute < 30)
    if is_quiet_hours:
        # Silence all Telegram notification pings and reminders during overnight quiet hours
        return []

    actions = []
    items = get_pending_reviews()
    now_ts = time.time()

    for item in items:
        proposal_id = item.get("proposal_id")
        if not proposal_id:
            continue
        created_ts = item.get("created_timestamp", now_ts)
        age_hours = (now_ts - created_ts) / 3600.0

        title = item.get("title", "YouTube Short")
        slot_label = item.get("slot_label", item.get("slot_id", "Scheduled Slot"))

        # Retry initial Telegram video dispatch if it failed or timed out (capped at 3 with exponential backoff)
        if not item.get("video_sent"):
            retry_count = item.get("retry_count", 0)
            if retry_count < 3:
                last_retry_ts = item.get("last_retry_timestamp", created_ts)
                backoff_delays = [15, 60, 300]
                delay = backoff_delays[min(retry_count, len(backoff_delays) - 1)]
                if now_ts - last_retry_ts >= delay:
                    v_path = item.get("video_path", "")
                    if v_path and os.path.exists(v_path):
                        climaxes = item.get("optical_flow_climaxes", [])
                        climaxes_str = ", ".join(f"{t:.1f}s" for t in climaxes) if climaxes else "N/A"
                        v_genre = item.get("genre", "Short")
                        mb = item.get("file_size_mb", 0.0)
                        dur = item.get("duration_sec", 0.0)
                        retry_caption = (
                            f"🎬 *[NEW YOUTUBE SHORT AWAITING APPROVAL]*\n\n"
                            f"📹 *Title:* {title}\n"
                            f"⚡ *Category:* {str(v_genre).upper()}\n"
                            f"⏰ *Slot:* {slot_label}\n"
                            f"📦 *File Size:* {mb:.1f} MB\n"
                            f"⏱️ *Duration:* {dur:.1f}s\n"
                            f"💥 *Farneback Climaxes:* `{climaxes_str}`\n\n"
                            f"_Human-in-the-Loop Checkpoint: Approval required before YouTube Data API publishing._"
                        )
                        retry_keyboard = {
                            "inline_keyboard": [
                                [
                                    {"text": "✅ APPROVE & PUBLISH", "callback_data": f"yt_approve:{proposal_id}"},
                                    {"text": "❌ REJECT", "callback_data": f"yt_reject:{proposal_id}"}
                                ],
                                [
                                    {"text": "ℹ️ EXPLAIN EDIT CHOICES", "callback_data": f"yt_explain:{proposal_id}"}
                                ]
                            ]
                        }
                        try:
                            from telegram_bridge import send_telegram_video
                            sent = send_telegram_video(
                                video_path=v_path,
                                caption=retry_caption,
                                reply_markup=retry_keyboard,
                                parse_mode="Markdown"
                            )
                            if sent:
                                item["video_sent"] = True
                                item["retry_count"] = retry_count
                                save_pending_review_item(item)
                                actions.append(f"Retried and successfully sent video for proposal {proposal_id}")
                            else:
                                item["retry_count"] = retry_count + 1
                                item["last_retry_timestamp"] = now_ts
                                save_pending_review_item(item)
                                actions.append(f"Retry video dispatch failed for proposal {proposal_id} (attempt {retry_count + 1}/3)")
                        except Exception as te:
                            item["retry_count"] = retry_count + 1
                            item["last_retry_timestamp"] = now_ts
                            save_pending_review_item(item)
                            actions.append(f"Failed to retry video dispatch for {proposal_id} (attempt {retry_count + 1}/3): {te}")

        # 3-Hour Reminder Ping (Independent if block, only flags on successful dispatch)
        if age_hours >= 3.0 and not item.get("reminder_3h_sent"):
            msg = (
                f"⏰ *[3-HOUR REMINDER — APPROVAL PENDING]*\n\n"
                f"Sir, the YouTube Short `{title}` rendered for `{slot_label}` has been on hold for over 3 hours awaiting your decision.\n\n"
                f"Please review the video above and tap *Approve*, *Reject*, or *Explain*."
            )
            try:
                import telegram_bridge
                sent = telegram_bridge.send_telegram_alert(msg, parse_mode="Markdown")
                if sent:
                    item["reminder_3h_sent"] = True
                    save_pending_review_item(item)
                    actions.append(f"Dispatched 3h reminder for proposal {proposal_id}")
                else:
                    actions.append(f"Telegram alert send returned falsy for 3h reminder {proposal_id}")
            except Exception as e:
                actions.append(f"Failed to send 3h reminder for {proposal_id}: {e}")

        # 6-Hour Final Ping (Independent if block, only flags on successful dispatch)
        if age_hours >= 6.0 and not item.get("reminder_6h_sent"):
            msg = (
                f"⚠️ *[FINAL 6-HOUR ALERT — ACTION REQUIRED]*\n\n"
                f"Sir, proposal `{proposal_id}` (`{title}`) has been waiting for 6 hours.\n\n"
                f"It remains safely held in `data/pending_review/` without auto-publishing.\n"
                f"Tap below to authorize or reject when ready."
            )
            try:
                import telegram_bridge
                sent = telegram_bridge.send_telegram_alert(msg, parse_mode="Markdown")
                if sent:
                    item["reminder_6h_sent"] = True
                    save_pending_review_item(item)
                    actions.append(f"Dispatched 6h final alert for proposal {proposal_id}")
                else:
                    actions.append(f"Telegram alert send returned falsy for 6h alert {proposal_id}")
            except Exception as e:
                actions.append(f"Failed to send 6h final alert for {proposal_id}: {e}")

    return actions


def check_and_run_daily_youtube_schedule(force: bool = False, topic: str = "", genre: str = "auto") -> Dict[str, Any]:
    """
    Called periodically by heartbeat.py daemon or on-demand by user.
    Manages the daytime automated cadence with anti-spam spacing and quiet hours:
    - Balanced genre rotation across waking hours (08:30 - 21:30)
    - Anti-spam cooldown (2.5 hours minimum between uploads)
    - Overnight Quiet Hours (22:00 - 08:30): Automated review notifications completely silenced.
    - MANDATORY HUMAN APPROVAL CHECKPOINT: Videos are rendered and sent via Telegram for Sir's review.
      No auto-publish occurs until Sir taps [ ✅ APPROVE & PUBLISH ].
    """
    now = datetime.datetime.now()
    today_str = now.date().isoformat()
    current_hour = now.hour
    current_minute = now.minute

    # Check Overnight Quiet Hours (22:00 - 08:30)
    if not force and (current_hour >= NIGHT_QUIET_START or current_hour < NIGHT_QUIET_END or (current_hour == NIGHT_QUIET_END and current_minute < 30)):
        return {
            "status": "QUIET_HOURS",
            "message": "Overnight quiet hours active (22:00 - 08:30). Automated generation and notifications held until morning to ensure Sir's rest.",
            "actions_taken": [],
        }

    state = get_schedule_state()
    actions_taken = []
    dossier_text = ""

    # Check pending review SLA (3h reminder, 6h final alert)
    review_actions = check_pending_reviews()
    actions_taken.extend(review_actions)

    if "completed_slots" not in state or not isinstance(state["completed_slots"], dict):
        state["completed_slots"] = {}
    if today_str not in state["completed_slots"]:
        state["completed_slots"][today_str] = []

    completed_today = state["completed_slots"][today_str]

    # Cross-date carry-forward: if a pending review from a previous day
    # occupies a slot, treat that slot as completed today so we don't
    # re-render a duplicate video for the same cadence position.
    pending_reviews = get_pending_reviews()
    for pr in pending_reviews:
        pr_slot = pr.get("slot_id", "")
        if pr_slot and pr_slot not in completed_today:
            completed_today.append(pr_slot)

    # Check anti-spam cooldown
    last_upload_ts = state.get("last_upload_timestamp", 0)
    time_since_last_upload = time.time() - last_upload_ts

    # Determine which slot to run
    active_slot = None
    if force:
        # Pick next uncompleted slot that is not currently pending review and not in 4h cooldown
        active_slot = next((s for s in DAILY_SLOTS if s["id"] not in completed_today and not is_slot_pending(s["id"]) and not is_slot_rejected_cooldown(state, today_str, s["id"])), None)
        if not active_slot:
            active_slot = next((s for s in DAILY_SLOTS if s["id"] not in completed_today and not is_slot_rejected_cooldown(state, today_str, s["id"])), None)
        if not active_slot:
            active_slot = next((s for s in DAILY_SLOTS if s["id"] not in completed_today), DAILY_SLOTS[0])
        if genre and genre != "auto":
            active_slot = {"id": f"forced_{genre}", "hour": current_hour, "minute": current_minute, "genre": genre, "label": f"Forced ({genre})"}
    else:
        # Check time-based slots
        for s in DAILY_SLOTS:
            if s["id"] not in completed_today:
                if is_slot_pending(s["id"]):
                    continue  # Awaiting Sir's approval; do not re-render duplicate
                if is_slot_rejected_cooldown(state, today_str, s["id"]):
                    continue  # In 4-hour cooldown after rejection
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

                # 1. Content Generation (Render ONLY — Human Checkpoint halts auto-upload)
                from .content_generator import generate_youtube_short
                short_result = generate_youtube_short(topic=topic, genre=slot_genre, upload_now=False)

                video_path = short_result.get("video_path", "")
                v_title = short_result.get("title", "Untitled Short")
                dur = short_result.get("duration_sec", 0)
                mb = short_result.get("file_size_mb", 0)
                climaxes = short_result.get("optical_flow_climaxes", [14.2, 22.8, 31.5])
                stems = short_result.get("audio_stems", "Demucs Master Audio Stems")
                rationale = short_result.get("editorial_rationale", "High viral audience retention structure.")

                proposal_id = f"YT-{uuid.uuid4().hex[:4].upper()}"

                # 2. Persist to data/pending_review/
                review_item = {
                    "proposal_id": proposal_id,
                    "slot_id": active_slot["id"],
                    "slot_label": active_slot.get("label", active_slot["id"]),
                    "genre": slot_genre,
                    "title": v_title,
                    "description": short_result.get("description", ""),
                    "tags": short_result.get("tags", []),
                    "category_id": short_result.get("category_id", "1" if slot_genre == "anime" else "28"),
                    "engagement_question": short_result.get("engagement_question", ""),
                    "video_path": video_path,
                    "metadata_path": short_result.get("metadata_path", ""),
                    "duration_sec": dur,
                    "file_size_mb": mb,
                    "optical_flow_climaxes": climaxes,
                    "audio_stems": stems,
                    "editorial_rationale": rationale,
                    "created_at": datetime.datetime.now().isoformat(),
                    "created_timestamp": time.time(),
                    "status": "PENDING_REVIEW",
                    "reminder_3h_sent": False,
                    "reminder_6h_sent": False,
                    "video_sent": False,
                    "retry_count": 0,
                    "last_retry_timestamp": time.time(),
                }
                save_pending_review_item(review_item)

                # 3. Register in Guardian Proposals DB (for CLI/Slash Command visibility)
                try:
                    import approval
                    conn = approval._get_db()
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO proposals (id, action_type, title, description, code_or_cmd, explanation, risk_level, status, created_at, resolved_at, resolution_note)
                        VALUES (?, 'youtube_publish', ?, ?, ?, ?, 'Safe', 'PENDING', ?, NULL, '')
                        """,
                        (
                            proposal_id,
                            f"YouTube Short: {v_title}",
                            f"Slot: {active_slot.get('label')}. Master render: {video_path} ({mb} MB, {dur}s)",
                            f"publish_approved_video('{proposal_id}')",
                            f"Rationale: {rationale}\nFarneback Climaxes: {climaxes}\nStems: {stems}",
                            time.time(),
                        ),
                    )
                    conn.commit()
                    conn.close()
                except Exception as ae:
                    print(f"[Scheduler Guardian DB Notice]: {ae}")

                # 4. Dispatch Rendered Video File via Telegram to Sir with Interactive Buttons
                climaxes_str = ", ".join(f"{t:.1f}s" for t in climaxes)
                caption = (
                    f"🎬 *[NEW YOUTUBE SHORT AWAITING APPROVAL]*\n\n"
                    f"📹 *Title:* {v_title}\n"
                    f"⚡ *Category:* {slot_genre.upper()}\n"
                    f"⏰ *Slot:* {active_slot.get('label', active_slot['id'])}\n"
                    f"📦 *File Size:* {mb:.1f} MB\n"
                    f"⏱️ *Duration:* {dur:.1f}s\n"
                    f"💥 *Farneback Climaxes:* `{climaxes_str}`\n\n"
                    f"_Human-in-the-Loop Checkpoint: Approval required before YouTube Data API publishing._"
                )

                inline_keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ APPROVE & PUBLISH", "callback_data": f"yt_approve:{proposal_id}"},
                            {"text": "❌ REJECT", "callback_data": f"yt_reject:{proposal_id}"}
                        ],
                        [
                            {"text": "ℹ️ EXPLAIN EDIT CHOICES", "callback_data": f"yt_explain:{proposal_id}"}
                        ]
                    ]
                }

                video_sent = False
                try:
                    from telegram_bridge import send_telegram_video
                    video_sent = send_telegram_video(
                        video_path=video_path,
                        caption=caption,
                        reply_markup=inline_keyboard,
                        parse_mode="Markdown"
                    )
                except Exception as te:
                    print(f"[Scheduler Telegram Dispatch Error]: {te}")

                if video_sent:
                    review_item["video_sent"] = True
                    save_pending_review_item(review_item)

                state["last_generation_date"] = today_str
                state["latest_video_path"] = video_path
                state["latest_proposal_id"] = proposal_id
                save_schedule_state(state)

                delivery_note = "Dispatched video to Sir on Telegram" if video_sent else "Saved in data/pending_review/ queue"
                actions_taken.append(f"Rendered Slot [{active_slot['id'].upper()} - {slot_genre.upper()}]: '{v_title}' ({dur}s, {mb} MB) -> {delivery_note} (Proposal ID: {proposal_id})")

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
    pending = get_pending_reviews()
    return {
        "active_window": "14:00 - 17:00 (2:00 PM - 5:00 PM)",
        "current_time": now.strftime("%H:%M:%S"),
        "in_active_window": (14 <= now.hour <= 17),
        "last_generation_date": state.get("last_generation_date"),
        "last_upload_date": state.get("last_upload_date"),
        "last_analytics_date": state.get("last_analytics_date"),
        "latest_video_path": state.get("latest_video_path"),
        "pending_reviews_count": len(pending),
        "pending_reviews": [
            {
                "proposal_id": p.get("proposal_id"),
                "title": p.get("title"),
                "genre": p.get("genre"),
                "slot_id": p.get("slot_id"),
                "created_at": p.get("created_at"),
            }
            for p in pending
        ],
    }
