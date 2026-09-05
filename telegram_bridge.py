"""
Z.A.I.N.E — Pocket Zaine (Private Mobile Telegram Bridge)
Provides secure remote access to Z.A.I.N.E via Telegram.
Supports text chat, voice notes (Whisper transcribed), system telemetry,
email check, and workspace task execution with strict whitelist authentication.
"""

import os
import time
import tempfile
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
TELEGRAM_PAIR_PIN = os.getenv("TELEGRAM_PAIR_PIN", "7788").strip()

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
FILE_BASE = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"

ENV_PATH = Path(__file__).parent / ".env"


def _update_env_user_id(user_id: str):
    """Saves the authenticated Telegram user ID to .env permanently."""
    global TELEGRAM_ALLOWED_USER_ID
    TELEGRAM_ALLOWED_USER_ID = str(user_id)
    if ENV_PATH.exists():
        content = ENV_PATH.read_text(encoding="utf-8")
        if "TELEGRAM_ALLOWED_USER_ID=" in content:
            lines = []
            for line in content.splitlines():
                if line.startswith("TELEGRAM_ALLOWED_USER_ID="):
                    lines.append(f"TELEGRAM_ALLOWED_USER_ID={user_id}")
                else:
                    lines.append(line)
            ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            with open(ENV_PATH, "a", encoding="utf-8") as f:
                f.write(f"\nTELEGRAM_ALLOWED_USER_ID={user_id}\n")


def send_telegram_alert(text: str, parse_mode: str = "") -> bool:
    """
    Sends a proactive alert or notification to the paired Telegram user.
    Can be invoked from anywhere (Heartbeat daemon, long tasks, etc.).
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or TELEGRAM_BOT_TOKEN
    target_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip() or TELEGRAM_ALLOWED_USER_ID
    if not token or not target_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram Alert Error]: {e}")
        return False


def send_telegram_photo(photo_bytes: bytes, caption: str = "") -> bool:
    """Sends a photo directly to the paired Telegram user."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or TELEGRAM_BOT_TOKEN
    target_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip() or TELEGRAM_ALLOWED_USER_ID
    if not token or not target_id or not photo_bytes:
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    files = {"photo": ("snapshot.jpg", photo_bytes, "image/jpeg")}
    data = {"chat_id": target_id}
    if caption:
        data["caption"] = caption

    try:
        resp = requests.post(url, data=data, files=files, timeout=20)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram Photo Error]: {e}")
        return False


class TelegramBridge:
    def __init__(self, agent=None):
        if agent is None:
            from agent import ZaineAgent
            self.agent = ZaineAgent()
        else:
            self.agent = agent

        self.whisper_model = None

    def _get_whisper(self):
        """Lazy loads Faster-Whisper only when a voice note is received."""
        if self.whisper_model is None:
            from faster_whisper import WhisperModel
            # Uses base.en or tiny on GPU/CPU for instant mobile voice note decoding
            self.whisper_model = WhisperModel("base.en", device="auto", compute_type="auto")
        return self.whisper_model

    def send_message(self, chat_id: int, text: str, parse_mode: str = ""):
        """Sends a text message to the specified Telegram chat."""
        url = f"{API_BASE}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            requests.post(url, json=payload, timeout=15)
        except Exception as e:
            print(f"[Telegram Error sending message]: {e}")

    def send_photo(self, chat_id: int, photo_bytes: bytes, caption: str = ""):
        """Sends a photo/image directly to the specified Telegram chat."""
        url = f"{API_BASE}/sendPhoto"
        files = {"photo": ("snapshot.jpg", photo_bytes, "image/jpeg")}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        try:
            requests.post(url, data=data, files=files, timeout=25)
        except Exception as e:
            print(f"[Telegram Error sending photo]: {e}")

    def send_chat_action(self, chat_id: int, action: str = "typing"):
        """Displays 'typing' or 'record_voice' status in Telegram."""
        url = f"{API_BASE}/sendChatAction"
        try:
            requests.post(url, json={"chat_id": chat_id, "action": action}, timeout=5)
        except Exception:
            pass

    def get_updates(self, offset: int = None, timeout: int = 25) -> list:
        """Fetches incoming Telegram messages via long polling."""
        url = f"{API_BASE}/getUpdates"
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        try:
            resp = requests.get(url, params=params, timeout=timeout + 5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return data.get("result", [])
        except Exception:
            pass
        return []

    def download_file(self, file_id: str) -> bytes:
        """Downloads a file (e.g. voice message) from Telegram servers."""
        url = f"{API_BASE}/getFile"
        resp = requests.get(url, params={"file_id": file_id}, timeout=15).json()
        if resp.get("ok"):
            file_path = resp["result"]["file_path"]
            download_url = f"{FILE_BASE}/{file_path}"
            r = requests.get(download_url, timeout=30)
            if r.status_code == 200:
                return r.content
        return b""

    def handle_voice_message(self, chat_id: int, voice_info: dict):
        """Processes an incoming voice note using Faster-Whisper."""
        self.send_chat_action(chat_id, "record_voice")
        file_id = voice_info.get("file_id")
        audio_data = self.download_file(file_id)
        if not audio_data:
            self.send_message(chat_id, "⚠️ Could not download voice message.")
            return

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name

        try:
            whisper = self._get_whisper()
            segments, _ = whisper.transcribe(tmp_path, beam_size=3)
            transcribed_text = " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as e:
            transcribed_text = ""
            print(f"[Whisper Transcribe Error]: {e}")
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        if not transcribed_text:
            self.send_message(chat_id, "⚠️ Could not transcribe audio. Please try again or type.")
            return

        self.send_message(chat_id, f"🎙️ *You said:* \"_{transcribed_text}_\"", parse_mode="Markdown")
        self.handle_text_message(chat_id, transcribed_text)

    def handle_photo_message(self, chat_id: int, photo_list: list, caption: str = ""):
        """Processes an incoming photo sent from phone using local Moondream vision."""
        self.send_chat_action(chat_id, "typing")
        if not photo_list:
            return
        photo_info = photo_list[-1]
        file_id = photo_info.get("file_id")
        photo_bytes = self.download_file(file_id)
        if not photo_bytes:
            self.send_message(chat_id, "⚠️ Could not download photo.")
            return

        import base64
        from vision import analyze_image_with_ollama
        b64_img = base64.b64encode(photo_bytes).decode("utf-8")
        prompt = caption.strip() if caption.strip() else "Describe what you see in this photo in detail."
        self.send_message(chat_id, "🔍 *Analyzing visual input with Moondream VLM...*", parse_mode="Markdown")
        analysis = analyze_image_with_ollama(b64_img, prompt=prompt)
        self.send_message(chat_id, f"👁️ *Visual Perception:*\n\n{analysis}", parse_mode="Markdown")

    def handle_text_message(self, chat_id: int, text: str):
        """Processes a text command through Z.A.I.N.E Agent."""
        clean = text.strip()
        if not clean:
            return

        # Slash Command Shortcuts
        if clean == "/start":
            welcome = (
                "👋 *Assalamu Alaikum, Mateen sir!*\n\n"
                "I am **Z.A.I.N.E**, your personal AI companion & system engineer.\n\n"
                "⚡ *Quick Commands:*\n"
                "• `/status` — Battery, CPU & RAM health\n"
                "• `/emails` — Check unread Gmail inbox\n"
                "• `/tasks` — View active task list\n"
                "• `/clear` — Reset session conversation\n\n"
                "You can send me any question, script instruction, or voice note!"
            )
            self.send_message(chat_id, welcome, parse_mode="Markdown")
            return

        elif clean == "/status":
            from tools import system_status
            status = system_status()
            self.send_message(chat_id, f"💻 *Hardware Status:*\n\n{status}", parse_mode="Markdown")
            return

        elif clean == "/emails":
            self.send_chat_action(chat_id, "typing")
            from tools import TOOL_REGISTRY
            check_fn = TOOL_REGISTRY.get("check_emails")
            if check_fn:
                res = check_fn(unread_only=True, limit=5)
                self.send_message(chat_id, f"📧 *Inbox Summary:*\n\n{res}")
            else:
                self.send_message(chat_id, "Email client not available.")
            return

        elif clean == "/tasks":
            from tools import list_tasks
            tasks = list_tasks()
            self.send_message(chat_id, f"📋 *Tasks:*\n\n{tasks}")
            return

        elif clean == "/reminders":
            from tools import list_reminders
            rems = list_reminders()
            self.send_message(chat_id, f"⏰ {rems}")
            return

        elif clean.startswith("/remind"):
            args = clean.replace("/remind", "", 1).strip()
            if "|" not in args:
                self.send_message(
                    chat_id,
                    "Usage: `/remind <time> | <message>`\nExample: `/remind in 20 mins | Call client`",
                    parse_mode="Markdown",
                )
            else:
                t_str, msg = args.split("|", 1)
                from tools import set_reminder
                res = set_reminder(msg.strip(), t_str.strip())
                self.send_message(chat_id, f"⏰ {res}")
            return

        elif clean == "/notes":
            from vault import list_vault_documents
            docs = list_vault_documents()
            self.send_message(chat_id, f"📚 {docs}")
            return

        elif clean.startswith("/vault"):
            query = clean.replace("/vault", "", 1).strip()
            if not query:
                self.send_message(chat_id, "Usage: `/vault <search_query>`", parse_mode="Markdown")
            else:
                self.send_chat_action(chat_id, "typing")
                from vault import search_vault
                results = search_vault(query)
                self.send_message(chat_id, f"🧠 *Vault Results:*\n\n{results}")
            return

        elif clean.startswith("/addnote"):
            args = clean.replace("/addnote", "", 1).strip()
            if "|" not in args:
                self.send_message(
                    chat_id,
                    "Usage: `/addnote <title> | <content>`\nExample: `/addnote Idea | Deploy on Pi 5`",
                    parse_mode="Markdown",
                )
            else:
                title, content = args.split("|", 1)
                from vault import add_to_vault
                res = add_to_vault(title.strip(), content.strip())
                self.send_message(chat_id, f"📝 {res}")
            return

        elif clean == "/screen":
            self.send_chat_action(chat_id, "upload_photo")
            from vision import capture_screen_bytes
            scr = capture_screen_bytes()
            if scr:
                self.send_photo(chat_id, scr, caption="🖥️ *Live Desktop Screen Capture*")
            else:
                self.send_message(
                    chat_id,
                    "🖥️ *Display Standby:*\nThe desktop screen is currently sleeping or the workstation is locked. Once the screen is active, I will be able to capture it.",
                    parse_mode="Markdown",
                )
            return

        elif clean == "/camera":
            self.send_chat_action(chat_id, "upload_photo")
            from vision import capture_webcam_bytes
            cam = capture_webcam_bytes()
            if cam:
                self.send_photo(chat_id, cam, caption="📷 *Live 1-Shot Webcam Photo*")
            else:
                self.send_message(chat_id, "⚠️ Could not access webcam. Ensure camera is connected.")
            return

        elif clean == "/clear":
            self.agent.memory.clear()
            self.send_message(chat_id, "🧹 Conversation context cleared.")
            return

        elif clean in ("/help", "/commands"):
            help_text = (
                r"⚡ *Z.A.I.N.E Pocket Commands:*" + "\n\n"
                r"• `/status` — Live hardware telemetry" + "\n"
                r"• `/screen` — Live desktop screenshot" + "\n"
                r"• `/camera` — 1-shot laptop webcam snapshot" + "\n"
                r"• `/emails` — Check unread Gmail inbox" + "\n"
                r"• `/tasks` — View active task list" + "\n"
                r"• `/remind <time> | <msg>` — Set alarm/reminder" + "\n"
                r"• `/reminders` — View scheduled alarms" + "\n"
                r"• `/vault <query>` — Search Personal Second Brain" + "\n"
                r"• `/notes` — List saved Second Brain docs" + "\n"
                r"• `/addnote <title> | <msg>` — Save note to vault" + "\n"
                r"• `/clear` — Reset conversation context" + "\n\n"
                "You can also chat freely in English or Urdu/Hindi, or send voice notes!"
            )
            self.send_message(chat_id, help_text, parse_mode="Markdown")
            return

        # General LLM query / Autonomous tool calling
        self.send_chat_action(chat_id, "typing")
        try:
            reply = self.agent.chat(clean)
            self.send_message(chat_id, reply)
        except Exception as e:
            self.send_message(chat_id, f"⚠️ Error processing command: {e}")

    def register_bot_commands(self):
        """Registers slash command autocomplete menu in Telegram client."""
        commands = [
            {"command": "status", "description": "Hardware telemetry (CPU, RAM, Battery)"},
            {"command": "screen", "description": "Live desktop screenshot"},
            {"command": "camera", "description": "1-shot laptop webcam snapshot"},
            {"command": "remind", "description": "Set reminder (<time> | <msg>)"},
            {"command": "reminders", "description": "View scheduled reminders"},
            {"command": "vault", "description": "Search personal Second Brain"},
            {"command": "addnote", "description": "Save note (<title> | <content>)"},
            {"command": "notes", "description": "List Second Brain notes"},
            {"command": "emails", "description": "Check unread Gmails"},
            {"command": "tasks", "description": "View active tasks"},
            {"command": "clear", "description": "Clear conversation memory"},
            {"command": "help", "description": "Commands guide"},
        ]
        try:
            r = requests.post(f"{API_BASE}/setMyCommands", json={"commands": commands}, timeout=10)
            if r.status_code == 200 and r.json().get("ok"):
                print("[Pocket Zaine]: Registered Telegram slash commands autocomplete.")
        except Exception:
            pass

    def run_polling(self):
        """Main polling loop for incoming Telegram messages."""
        if not TELEGRAM_BOT_TOKEN:
            print("[Pocket Zaine]: TELEGRAM_BOT_TOKEN not set in .env. Bridge inactive.")
            return

        # Verify bot identity
        try:
            me = requests.get(f"{API_BASE}/getMe", timeout=10).json()
            if not me.get("ok"):
                print(f"[Pocket Zaine Error]: Invalid Bot Token: {me.get('description')}")
                return
            bot_username = me["result"].get("username", "ZaineBot")
            print(f"\n[Pocket Zaine Online]: Connected to @{bot_username}")
            print(f"[Pocket Zaine Security]: Allowed User ID = '{TELEGRAM_ALLOWED_USER_ID or 'Not paired (send /pair <PIN>)'}'\n")
            self.register_bot_commands()
        except Exception as e:
            print(f"[Pocket Zaine Error connecting]: {e}")
            return

        offset = None
        while True:
            try:
                updates = self.get_updates(offset=offset, timeout=20)
                for u in updates:
                    offset = u["update_id"] + 1
                    msg = u.get("message")
                    if not msg:
                        continue

                    chat_id = msg["chat"]["id"]
                    from_user = msg.get("from", {})
                    user_id = str(from_user.get("id", ""))
                    username = from_user.get("username", "Unknown")

                    # --- Security & Whitelist Authentication ---
                    if TELEGRAM_ALLOWED_USER_ID:
                        if user_id != TELEGRAM_ALLOWED_USER_ID:
                            print(f"[Pocket Zaine Security Alert]: Blocked unauthorized message from @{username} (ID: {user_id})")
                            self.send_message(chat_id, "⛔ *Access Denied.*\nZ.A.I.N.E is private and restricted to Mateen only.", parse_mode="Markdown")
                            continue
                    else:
                        # Pairing mode
                        text = msg.get("text", "").strip()
                        if text.startswith("/pair"):
                            parts = text.split()
                            if len(parts) == 2 and parts[1] == TELEGRAM_PAIR_PIN:
                                _update_env_user_id(user_id)
                                print(f"[Pocket Zaine]: Successfully paired with @{username} (ID: {user_id})!")
                                self.send_message(
                                    chat_id,
                                    f"✅ *Pairing Successful!*\n\nWelcome Mateen sir! Z.A.I.N.E is now permanently locked to this account (ID: `{user_id}`).",
                                    parse_mode="Markdown",
                                )
                                continue
                            else:
                                self.send_message(chat_id, "❌ Invalid PIN. Use `/pair <PIN>` to authenticate.", parse_mode="Markdown")
                                continue
                        else:
                            self.send_message(
                                chat_id,
                                f"🔒 *Z.A.I.N.E is Locked.*\nPlease pair your account by sending:\n`/pair {TELEGRAM_PAIR_PIN}`",
                                parse_mode="Markdown",
                            )
                            continue

                    # --- Authenticated User Message Handling ---
                    if "voice" in msg:
                        self.handle_voice_message(chat_id, msg["voice"])
                    elif "photo" in msg:
                        self.handle_photo_message(chat_id, msg["photo"], caption=msg.get("caption", ""))
                    elif "text" in msg:
                        self.handle_text_message(chat_id, msg["text"])

            except Exception:
                time.sleep(2)


if __name__ == "__main__":
    try:
        from heartbeat import heartbeat_daemon
        heartbeat_daemon.start()
        print("[Pocket Zaine]: Proactive Heartbeat Daemon started in background.")
    except Exception as e:
        print(f"[Heartbeat Startup Notice]: {e}")

    bridge = TelegramBridge()
    bridge.run_polling()
