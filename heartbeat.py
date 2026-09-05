"""
Z.A.I.N.E — Proactive Heartbeat Daemon (Phase 4 Upgraded)
Runs continuously in the background while Zaine is idle to monitor:
1. Jarvis Scheduled Reminders & Alarms: Due timer execution (speech + Telegram)
2. Battery Sentinel: Low battery warning (< 20% on battery)
3. Daily Morning Briefing: Unread Gmails + Pending Tasks (08:00–11:30 AM)
4. Evening Debrief & Sign-off: Daily wrap-up + server cleanup reminder (21:00–23:30 PM)
5. Hardware Sentinel: Low disk space (< 10GB) alerts
6. Ergonomics Sentinel: 90-minute continuous work & hydration break reminders
7. Smart Night Mode: Whisper-quiet operation between 00:00 and 07:00 (mutes TTS, silent push only)
"""

import time
import shutil
import datetime
import threading
import psutil
from dotenv import load_dotenv

load_dotenv()

try:
    from telegram_bridge import send_telegram_alert
except Exception:
    send_telegram_alert = lambda text, parse_mode="": False

try:
    from voice import speak_sentence, is_speaking
except Exception:
    speak_sentence = lambda text: True
    is_speaking = lambda: False


class HeartbeatDaemon:
    def __init__(self, check_interval_seconds: int = 15):
        self.check_interval = check_interval_seconds
        self.stop_event = threading.Event()
        self.thread = None

        # Tracking state
        self.last_battery_alert_time = 0
        self.last_battery_percent = 100
        self.last_briefing_date = None
        self.last_evening_debrief_date = None
        self.last_disk_alert_date = None
        self.session_start_time = time.time()
        self.last_ergonomics_reminder_time = time.time()
        self.user_last_active_time = time.time()

    def record_activity(self):
        """Called whenever the user interacts with Zaine to track active sessions."""
        self.user_last_active_time = time.time()

    def is_night_mode(self) -> bool:
        """Returns True between 00:00 and 07:00 AM for sleep quiet hours."""
        hour = datetime.datetime.now().hour
        return 0 <= hour < 7

    def check_reminders(self) -> list:
        """Checks and delivers due scheduled alarms/reminders."""
        delivered = []
        try:
            from tools import get_due_reminders, mark_reminder_triggered
            due = get_due_reminders()
            for r in due:
                rid = r["id"]
                msg = r["message"]

                # 1. Dispatch to Telegram
                send_telegram_alert(f"⏰ *Reminder:* {msg}", parse_mode="Markdown")

                # 2. Futuristic sci-fi chime (Windows winsound alert)
                try:
                    import winsound
                    winsound.Beep(1320, 140)  # E6 note
                    winsound.Beep(1760, 220)  # A6 note
                except Exception:
                    pass

                # 3. Speak aloud if not night mode and not already speaking
                if not self.is_night_mode() and not is_speaking():
                    try:
                        speak_sentence(f"Pardon the interruption, Sir. Scheduled reminder: {msg}")
                    except Exception:
                        pass

                # 4. Dispatch to Holographic HUD UI if running
                try:
                    import ui
                    active_ui = ui.get_ui()
                    if active_ui:
                        active_ui.append_message("system", f"⏰ REMINDER: {msg}")
                except Exception:
                    pass

                mark_reminder_triggered(rid)
                delivered.append(msg)
        except Exception as e:
            print(f"[Reminders Sentinel Error]: {e}")
        return delivered


    def check_battery(self) -> dict:
        """Inspects system battery and sends alerts if critical."""
        battery = psutil.sensors_battery()
        if not battery:
            return {"has_battery": False, "status": "No battery sensor detected (Desktop AC)"}

        percent = int(battery.percent)
        plugged = bool(battery.power_plugged)
        now = time.time()

        result = {
            "has_battery": True,
            "percent": percent,
            "plugged": plugged,
            "alert_sent": False,
        }

        if not plugged and percent <= 20:
            # Trigger alert if 30 minutes elapsed or battery dropped below 10%
            time_since_last = now - self.last_battery_alert_time
            if time_since_last > 1800 or (percent <= 10 and self.last_battery_percent > 10):
                msg = f"⚠️ *Battery Warning:* Laptop battery is down to {percent}%. Please connect the charger, Sir."
                send_telegram_alert(msg, parse_mode="Markdown")

                if not self.is_night_mode() and not is_speaking():
                    try:
                        speak_sentence(f"Sir, your laptop battery is at {percent} percent. Please connect your charger.")
                    except Exception:
                        pass

                self.last_battery_alert_time = now
                self.last_battery_percent = percent
                result["alert_sent"] = True

        return result

    def check_morning_briefing(self) -> dict:
        """Delivers a once-daily morning briefing between 08:00 and 11:30 AM."""
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        is_morning = 8 <= now.hour <= 11
        if not is_morning or self.last_briefing_date == today_str:
            return {"sent": False, "reason": "Outside window or already sent"}

        # Fetch unread emails
        email_summary = "Inbox clear"
        try:
            from email_client import check_emails
            raw_emails = check_emails(unread_only=True, limit=5)
            lines = [l.strip() for l in raw_emails.splitlines() if l.strip()]
            if lines and "No unread emails" not in lines[0]:
                email_summary = f"{len(lines)} unread emails pending"
            else:
                email_summary = "No new unread emails"
        except Exception as e:
            email_summary = f"Email check: {e}"

        # Fetch pending tasks
        task_summary = "All tasks complete"
        try:
            from tools import list_tasks
            raw_tasks = list_tasks(show_done=False)
            task_lines = [t.strip() for t in raw_tasks.splitlines() if t.strip() and not t.startswith("No tasks")]
            if task_lines:
                task_summary = f"{len(task_lines)} tasks queued"
        except Exception as e:
            task_summary = f"Task check: {e}"

        briefing_text = (
            f"🌅 *Good morning, Mateen sir!*\n\n"
            f"Here is your morning intelligence briefing:\n"
            f"• *Emails:* {email_summary}\n"
            f"• *Tasks:* {task_summary}\n\n"
            f"Z.A.I.N.E systems are fully primed. Ready whenever you are!"
        )

        send_telegram_alert(briefing_text, parse_mode="Markdown")

        if not self.is_night_mode() and not is_speaking():
            try:
                spoken = f"Good morning, Sir. You have {email_summary} and {task_summary}. Ready whenever you are."
                speak_sentence(spoken)
            except Exception:
                pass

        self.last_briefing_date = today_str
        return {"sent": True, "briefing": briefing_text}

    def check_evening_debrief(self) -> dict:
        """Delivers a daily evening wrap-up & sign-off between 21:00 and 23:30 PM."""
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        is_evening = (21 <= now.hour <= 23)
        if not is_evening or self.last_evening_debrief_date == today_str:
            return {"sent": False, "reason": "Outside evening window or already sent"}

        # Check pending tasks
        pending_count = 0
        try:
            from tools import list_tasks
            raw_tasks = list_tasks(show_done=False)
            task_lines = [t.strip() for t in raw_tasks.splitlines() if t.strip() and not t.startswith("No tasks")]
            pending_count = len(task_lines)
        except Exception:
            pass

        # Check if local servers are still open
        server_note = "All local servers idle."
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port in (8080, 8000) and conn.status == "LISTEN":
                server_note = f"Notice: Port {conn.laddr.port} server is still active."
                break

        debrief_text = (
            f"🌙 *Evening Wrap-up & Sign-off, Sir!*\n\n"
            f"• *Tasks:* {pending_count} pending tasks for tomorrow\n"
            f"• *Services:* {server_note}\n\n"
            f"Great work today. Zaine will remain on low-power standby. Good night!"
        )

        send_telegram_alert(debrief_text, parse_mode="Markdown")

        if not self.is_night_mode() and not is_speaking():
            try:
                speak_sentence(f"Good evening, Sir. You have {pending_count} tasks queued for tomorrow. Systems standing down to night mode. Have a restful night.")
            except Exception:
                pass

        self.last_evening_debrief_date = today_str
        return {"sent": True, "debrief": debrief_text}

    def check_disk_space(self) -> dict:
        """Checks free space on the primary system drive (C:)."""
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        if self.last_disk_alert_date == today_str:
            return {"alert_sent": False}

        try:
            total, used, free = shutil.disk_usage("C:\\")
            free_gb = free / (1024 ** 3)
            if free_gb < 10.0:
                alert_text = f"⚠️ *Storage Alert:* Low disk space on C: drive ({free_gb:.1f} GB remaining). Please clean temporary files."
                send_telegram_alert(alert_text, parse_mode="Markdown")
                self.last_disk_alert_date = today_str
                return {"alert_sent": True, "free_gb": free_gb}
        except Exception:
            pass
        return {"alert_sent": False}

    def check_ergonomics(self) -> dict:
        """Suggests hydration and eye breaks after 90 minutes of active continuous work."""
        now = time.time()
        active_duration = now - self.session_start_time
        time_since_reminder = now - self.last_ergonomics_reminder_time

        result = {"reminded": False}
        if active_duration >= 5400 and time_since_reminder >= 3600:  # 90 min session, 60 min cooldown
            reminder_text = (
                "💧 *Hydration & Posture Break:*\n"
                "Sir, you've been working intensely for over 90 minutes. "
                "Take a sip of water, stretch, and rest your eyes for a moment."
            )
            send_telegram_alert(reminder_text, parse_mode="Markdown")
            if not self.is_night_mode() and not is_speaking():
                try:
                    speak_sentence("Sir, you've been at the screen for 90 minutes. Remember to drink some water and stretch.")
                except Exception:
                    pass

            self.last_ergonomics_reminder_time = now
            result["reminded"] = True

        return result

    def check_desk_presence_sentinel(self) -> dict:
        """Welcomes the user when they return to the desk after being away for > 30 minutes."""
        now = time.time()
        if (now - self.user_last_active_time < 1800) or self.is_night_mode():
            return {"greeting_sent": False}

        try:
            from vision import check_desk_presence
            pres = check_desk_presence()
            if pres.get("present"):
                self.record_activity()
                if not is_speaking():
                    try:
                        speak_sentence("Welcome back, Sir. All systems standing by.")
                    except Exception:
                        pass
                return {"greeting_sent": True}
        except Exception:
            pass
        return {"greeting_sent": False}

    def check_youtube_studio_schedule(self) -> dict:
        """Executes the daily 14:00 - 17:00 autonomous YouTube Shorts creation, upload & analytics cycle."""
        try:
            from youtube_studio import check_and_run_daily_youtube_schedule
            return check_and_run_daily_youtube_schedule(force=False)
        except Exception as e:
            return {"ran": False, "error": str(e)}

    def run_cycle(self) -> dict:
        """Executes one complete sentinel inspection cycle."""
        rem_res = self.check_reminders()
        b_res = self.check_battery()
        m_res = self.check_morning_briefing()
        ev_res = self.check_evening_debrief()
        d_res = self.check_disk_space()
        e_res = self.check_ergonomics()
        pres_res = self.check_desk_presence_sentinel()
        yt_res = self.check_youtube_studio_schedule()

        return {
            "reminders_fired": rem_res,
            "battery": b_res,
            "morning_briefing": m_res,
            "evening_debrief": ev_res,
            "disk": d_res,
            "ergonomics": e_res,
            "desk_presence": pres_res,
            "youtube_studio": yt_res,
            "night_mode": self.is_night_mode(),
            "timestamp": datetime.datetime.now().isoformat(),
        }

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as e:
                print(f"[Heartbeat Daemon Error]: {e}")

            # Sleep in 1-second ticks for prompt shutdown response
            for _ in range(int(self.check_interval)):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

    def start(self):
        """Starts the Heartbeat Daemon in a background daemon thread."""
        if self.thread is not None and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, name="ZaineHeartbeatDaemon", daemon=True)
        self.thread.start()
        print("[Heartbeat Daemon]: Upgraded proactive intelligence monitor online.")

    def stop(self):
        """Stops the daemon."""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)


# Singleton instance for application-wide access
heartbeat_daemon = HeartbeatDaemon(check_interval_seconds=15)


def trigger_proactive_check() -> str:
    """Manually runs an immediate proactive heartbeat check and returns the status summary."""
    status = heartbeat_daemon.run_cycle()
    bat = status.get("battery", {})
    bat_str = f"{bat.get('percent', 'N/A')}% ({'Plugged' if bat.get('plugged') else 'On Battery'})" if bat.get("has_battery") else "AC Power"

    return (
        f"Proactive Heartbeat Status:\n"
        f"- Battery: {bat_str}\n"
        f"- Reminders Triggered: {len(status.get('reminders_fired', []))}\n"
        f"- Morning Briefing: {'Sent' if status['morning_briefing'].get('sent') else status['morning_briefing'].get('reason', 'Pending')}\n"
        f"- Evening Debrief: {'Sent' if status['evening_debrief'].get('sent') else status['evening_debrief'].get('reason', 'Pending')}\n"
        f"- Night Mode: {'Active (Whisper-Quiet)' if status['night_mode'] else 'Daytime Normal'}\n"
        f"- Ergonomics: {'Reminder issued' if status['ergonomics'].get('reminded') else 'Session normal'}\n"
        f"- Monitored At: {status['timestamp']}"
    )


if __name__ == "__main__":
    print("Testing Upgraded Heartbeat Daemon standalone run...")
    print(trigger_proactive_check())
