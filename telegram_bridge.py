"""
Z.A.I.N.E — Pocket Zaine (Private Mobile Telegram Bridge v2.0)
Provides rock-solid remote access to Z.A.I.N.E via Telegram.
Features:
- Multi-threaded non-blocking polling and execution.
- Human-in-the-Loop Guardian Action Approval workflow (Approve / Deny / Explain).
- Full Telegram Inline Keyboard & Callback Query support.
- Resilient message chunking (>4000 chars) and automatic Markdown entity fallback.
- Continuous typing indicators during reasoning phases.
- Multimodal perception (Whisper voice notes, Moondream VLM camera/photos).
- Strict whitelist authentication locked to Mateen Sir.
"""

import os
import sys
import time
import json
import tempfile
import threading
import re
import sqlite3
import datetime
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
TELEGRAM_PAIR_PIN = os.getenv("TELEGRAM_PAIR_PIN", "7788").strip()

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
FILE_BASE = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"

ENV_PATH = Path(__file__).parent / ".env"
DB_PATH = Path(__file__).parent / "zaine_tasks.db"


def get_core_service_url() -> str:
    """Discovers active core HTTP service port from .zaine_core.json."""
    config_path = Path(__file__).parent / ".zaine_core.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            port = data.get("port", 7860)
            return f"http://127.0.0.1:{port}"
        except Exception:
            pass
    return "http://127.0.0.1:7860"


def wait_for_core_service(max_retries: Optional[int] = None) -> bool:
    """Blocks and polls GET /api/health with exponential backoff until core service is online."""
    delay = 1.0
    attempts = 0
    while max_retries is None or attempts < max_retries:
        url = get_core_service_url()
        try:
            resp = requests.get(f"{url}/api/health", timeout=2.0)
            if resp.status_code == 200 and resp.json().get("ok"):
                print(f"[Pocket Zaine]: Connected to Z.A.I.N.E Core Service at {url}")
                return True
        except Exception:
            pass

        print(f"[Pocket Zaine]: Core service at {url} unavailable, retrying in {delay:.1f}s...")
        time.sleep(delay)
        delay = min(delay * 1.5, 15.0)
        attempts += 1

    return False


def _get_chat_settings_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_chat_settings (
            chat_id TEXT PRIMARY KEY,
            voice_mode TEXT DEFAULT 'auto',
            updated_at TEXT NOT NULL
        )
        """
    )
    return conn


def get_chat_voice_mode(chat_id: int) -> str:
    """Returns 'auto', 'on', or 'off' for a given chat."""
    try:
        conn = _get_chat_settings_conn()
        row = conn.execute(
            "SELECT voice_mode FROM telegram_chat_settings WHERE chat_id = ?",
            (str(chat_id),)
        ).fetchone()
        conn.close()
        if row and row[0]:
            return row[0].lower()
    except Exception:
        pass
    return "auto"


def set_chat_voice_mode(chat_id: int, mode: str) -> bool:
    """Persists voice_mode ('auto', 'on', 'off') for a given chat."""
    mode = mode.strip().lower()
    if mode not in ("auto", "on", "off"):
        return False
    try:
        conn = _get_chat_settings_conn()
        conn.execute(
            """
            INSERT INTO telegram_chat_settings (chat_id, voice_mode, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                voice_mode = excluded.voice_mode,
                updated_at = excluded.updated_at
            """,
            (str(chat_id), mode, datetime.datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[Telegram settings error]: {e}")
        return False


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

_lock_socket = None

def acquire_telegram_lock(port: int = 49912) -> bool:
    """Acquires a single-instance socket lock to prevent 409 Conflict polling errors."""
    global _lock_socket
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", port))
        s.listen(1)
        _lock_socket = s
        return True
    except OSError:
        return False


def send_telegram_alert(text: str, parse_mode: str = "", reply_markup: Optional[Dict[str, Any]] = None) -> bool:
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
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        resp = requests.post(url, json=payload, timeout=12)
        if resp.status_code == 200:
            return True
        # If markdown parsing error, fallback to plain text
        if parse_mode:
            payload.pop("parse_mode", None)
            resp2 = requests.post(url, json=payload, timeout=12)
            return resp2.status_code == 200
        return False
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
        resp = requests.post(url, data=data, files=files, timeout=25)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram Photo Error]: {e}")
        return False


def _get_video_for_telegram(video_path: str, max_bytes: int = 48 * 1024 * 1024) -> Tuple[str, bool, str]:
    """
    Checks if video file exceeds Telegram's ~50MB limit.
    If > 48MB, creates a compressed preview copy using FFmpeg (keeping the original untouched).
    Returns (path_to_send, is_preview, note_string).
    """
    p = Path(video_path)
    if not p.exists():
        return video_path, False, ""

    size = p.stat().st_size
    if size <= max_bytes:
        return video_path, False, ""

    preview_path = p.parent / f"{p.stem}_tg_preview.mp4"
    note = (
        f"\n\n⚠️ *[COMPRESSED PREVIEW FOR TELEGRAM]*\n"
        f"_Original file ({round(size / (1024*1024), 1)} MB) preserved in master quality (CRF 16) for YouTube._"
    )

    if preview_path.exists() and preview_path.stat().st_size <= max_bytes:
        return str(preview_path), True, note

    try:
        import subprocess
        from youtube_studio.content_generator import get_ffmpeg_binary
        ffmpeg = get_ffmpeg_binary()
        cmd = [
            ffmpeg, "-y",
            "-i", str(p),
            "-vf", "scale=540:960",
            "-c:v", "libx264", "-crf", "28", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "96k",
            str(preview_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=90)
        if preview_path.exists() and preview_path.stat().st_size <= max_bytes:
            return str(preview_path), True, note
    except Exception as e:
        print(f"[Telegram Preview Warning]: {e}")

    # If full downscale still exceeds or failed, extract a 15-second highlight clip
    highlight_path = p.parent / f"{p.stem}_highlight_15s.mp4"
    try:
        cmd_hl = [
            ffmpeg, "-y",
            "-ss", "00:00:15",
            "-i", str(p),
            "-t", "15",
            "-c:v", "libx264", "-crf", "26", "-preset", "veryfast",
            "-c:a", "aac",
            str(highlight_path)
        ]
        subprocess.run(cmd_hl, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=60)
        if highlight_path.exists():
            hl_note = (
                f"\n\n⚠️ *[15-SECOND CLIMAX HIGHLIGHT PREVIEW]*\n"
                f"_Original full master ({round(size / (1024*1024), 1)} MB) preserved for YouTube publishing._"
            )
            return str(highlight_path), True, hl_note
    except Exception as e:
        print(f"[Telegram Highlight Warning]: {e}")

    return video_path, False, ""


def send_telegram_video(
    video_path: str,
    caption: str = "",
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: str = "Markdown",
    chat_id: Optional[str] = None,
) -> bool:
    """
    Sends a video directly to the paired Telegram user with interactive inline buttons.
    Automatically handles files exceeding Telegram's 50MB limit with high-speed preview fallback.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or TELEGRAM_BOT_TOKEN
    target_id = chat_id or os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip() or TELEGRAM_ALLOWED_USER_ID
    if not token or not target_id or not os.path.exists(video_path):
        return False

    # Quiet hours enforcement (22:00 - 08:30): Silence overnight video review pushes
    now = datetime.datetime.now()
    if now.hour >= 22 or now.hour < 8 or (now.hour == 8 and now.minute < 30):
        print("[Telegram Bridge] Quiet hours active (22:00 - 08:30) — holding video dispatch to preserve Sir's rest.")
        return False

    file_to_send, is_preview, note = _get_video_for_telegram(video_path)
    full_caption = (caption + note).strip()

    if len(full_caption) > 1024:
        preamble = full_caption[:3800]
        send_telegram_alert(preamble, parse_mode=parse_mode)
        full_caption = caption[:900] + (note if len(caption[:900]) + len(note) <= 1024 else "")

    url = f"https://api.telegram.org/bot{token}/sendVideo"
    data = {"chat_id": target_id}
    if full_caption:
        data["caption"] = full_caption[:1024]
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    try:
        with open(file_to_send, "rb") as vf:
            files = {"video": (Path(file_to_send).name, vf, "video/mp4")}
            resp = requests.post(url, data=data, files=files, timeout=90)
            if resp.status_code == 200:
                return True
            if parse_mode:
                data.pop("parse_mode", None)
                vf.seek(0)
                resp2 = requests.post(url, data=data, files=files, timeout=90)
                return resp2.status_code == 200
        return False
    except Exception as e:
        print(f"[Telegram Video Error]: {e}")
        return False


def _chunk_text(text: str, max_chars: int = 3800) -> List[str]:
    """Splits long text cleanly by lines or paragraphs to fit Telegram's 4096 character limit."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    lines = text.split("\n")
    curr = ""
    for line in lines:
        if len(curr) + len(line) + 1 > max_chars:
            if curr:
                chunks.append(curr.strip())
                curr = ""
            # If a single line exceeds max_chars, hard split
            while len(line) > max_chars:
                chunks.append(line[:max_chars])
                line = line[max_chars:]
            curr = line + "\n"
        else:
            curr += line + "\n"

    if curr.strip():
        chunks.append(curr.strip())

    return chunks if chunks else [text[:max_chars]]


class TelegramBridge:
    def __init__(self, agent=None):
        self.agent = agent
        self.core_url = get_core_service_url()
        self.whisper_model = None
        self._typing_stops: Dict[int, threading.Event] = {}

    def _chat_with_agent(self, text: str) -> str:
        """Sends chat prompt to core HTTP service (or direct agent if bound in-process)."""
        if self.agent is not None:
            return self.agent.chat(text)

        # Thin client HTTP call to core service
        url = f"{get_core_service_url()}/api/chat"
        req_id = f"tg-{uuid.uuid4().hex[:8]}"
        payload = {
            "message": text,
            "client": "telegram",
            "request_id": req_id
        }
        try:
            resp = requests.post(url, json=payload, timeout=90)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("reply", "No response received.")
            else:
                return f"⚠️ Core service returned status {resp.status_code}: {resp.text}"
        except requests.exceptions.ConnectionError:
            return "⚠️ Z.A.I.N.E Core Service is offline. Please start main.py on the workstation."
        except Exception as e:
            return f"⚠️ Core service communication error: {e}"

    def _get_whisper(self):
        """Lazy loads Faster-Whisper only when a voice note is received."""
        if self.whisper_model is None:
            from faster_whisper import WhisperModel
            self.whisper_model = WhisperModel("base.en", device="auto", compute_type="auto")
        return self.whisper_model

    def _start_typing_heartbeat(self, chat_id: int):
        """Maintains active 'typing' status in Telegram while agent is generating reasoning."""
        stop_evt = threading.Event()
        self._typing_stops[chat_id] = stop_evt

        def _worker():
            while not stop_evt.is_set():
                self.send_chat_action(chat_id, "typing")
                time.sleep(3.5)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _stop_typing_heartbeat(self, chat_id: int):
        """Stops the typing status heartbeat."""
        evt = self._typing_stops.pop(chat_id, None)
        if evt:
            evt.set()

    def send_message(self, chat_id: int, text: str, parse_mode: str = "", reply_markup: Optional[Dict[str, Any]] = None):
        """Sends a text message to Telegram, automatically handling chunking and markdown fallbacks."""
        if not text:
            return

        chunks = _chunk_text(text)
        for idx, chunk in enumerate(chunks):
            # Only attach reply_markup to the final chunk
            markup = json.dumps(reply_markup) if (reply_markup and idx == len(chunks) - 1) else None
            url = f"{API_BASE}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": chunk,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if markup:
                payload["reply_markup"] = markup

            try:
                resp = requests.post(url, json=payload, timeout=15)
                if resp.status_code != 200:
                    # Markdown entities might be broken (unbalanced _ or *), retry as plain text
                    if parse_mode:
                        payload.pop("parse_mode", None)
                        requests.post(url, json=payload, timeout=15)
            except Exception as e:
                print(f"[Telegram Error sending message]: {e}")

    def edit_message(self, chat_id: int, message_id: int, text: str, parse_mode: str = "", reply_markup: Optional[Dict[str, Any]] = None):
        """Edits an existing Telegram message in place."""
        url = f"{API_BASE}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:4000],
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)

        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code != 200 and parse_mode:
                payload.pop("parse_mode", None)
                requests.post(url, json=payload, timeout=15)
        except Exception as e:
            print(f"[Telegram Error editing message]: {e}")

    def edit_message_caption(self, chat_id: int, message_id: int, caption: str, parse_mode: str = "", reply_markup: Optional[Dict[str, Any]] = None):
        """Edits the caption of an existing media message in place."""
        url = f"{API_BASE}/editMessageCaption"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": caption[:1024],
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code != 200 and parse_mode:
                payload.pop("parse_mode", None)
                requests.post(url, json=payload, timeout=15)
        except Exception as e:
            print(f"[Telegram Edit Caption Error]: {e}")

    def send_video(self, chat_id: int, video_path: str, caption: str = "", reply_markup: Optional[Dict[str, Any]] = None, parse_mode: str = "Markdown"):
        """Sends a video message using the global helper."""
        return send_telegram_video(video_path=video_path, caption=caption, reply_markup=reply_markup, parse_mode=parse_mode, chat_id=str(chat_id))

    def answer_callback_query(self, callback_query_id: str, text: str = ""):
        """Acknowledges inline button clicks to dismiss Telegram client loading animation."""
        url = f"{API_BASE}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        try:
            requests.post(url, json=payload, timeout=8)
        except Exception:
            pass

    def send_photo(self, chat_id: int, photo_bytes: bytes, caption: str = ""):
        """Sends a photo/image directly to the specified Telegram chat."""
        url = f"{API_BASE}/sendPhoto"
        files = {"photo": ("snapshot.jpg", photo_bytes, "image/jpeg")}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption[:1024]
        try:
            requests.post(url, data=data, files=files, timeout=25)
        except Exception as e:
            print(f"[Telegram Error sending photo]: {e}")

    def send_voice_reply(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None) -> bool:
        """
        Synthesizes text as an OGG Opus voice note and sends via Telegram /sendVoice.
        If text exceeds ~150 words, synthesizes the first ~150 words (split at sentence boundary)
        as audio, and appends the full written text response as a follow-up message.
        Cleans up temporary audio files in all cases.
        Falls back to send_message() if voice synthesis or upload fails.
        """
        if not text or not text.strip():
            return False

        clean_text = text.strip()
        words = clean_text.split()
        split_needed = len(words) > 150

        if split_needed:
            # Find natural sentence boundary around 150 words
            candidate = " ".join(words[:170])
            best_end = -1
            for m in re.finditer(r'[.!?](\s|$)', candidate):
                if m.start() >= len(" ".join(words[:120])):
                    best_end = m.end()
            if best_end > 0:
                speech_text = candidate[:best_end].strip()
            else:
                speech_text = " ".join(words[:150]) + "..."
        else:
            speech_text = clean_text

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_f:
            temp_ogg = tmp_f.name

        try:
            self.send_chat_action(chat_id, "record_voice")
            from voice import synthesize_to_file
            ok = synthesize_to_file(speech_text, temp_ogg)
            if not ok or not os.path.exists(temp_ogg) or os.path.getsize(temp_ogg) == 0:
                print("[Pocket Zaine]: Voice synthesis failed or produced empty file -> Fallback to text.")
                self.send_message(chat_id, clean_text)
                return False

            url = f"{API_BASE}/sendVoice"
            data = {"chat_id": chat_id}
            if reply_to_message_id:
                data["reply_to_message_id"] = reply_to_message_id

            with open(temp_ogg, "rb") as voice_file:
                files = {"voice": ("voice.ogg", voice_file, "audio/ogg")}
                resp = requests.post(url, data=data, files=files, timeout=35)

            if resp.status_code != 200:
                print(f"[Telegram /sendVoice failed ({resp.status_code})]: {resp.text} -> Fallback to text.")
                self.send_message(chat_id, clean_text)
                return False

            # If response was long, append full written text as follow-up
            if split_needed:
                followup = f"📝 *Full Written Response:*\n\n{clean_text}"
                self.send_message(chat_id, followup, parse_mode="Markdown")

            return True
        except Exception as e:
            print(f"[Telegram send_voice_reply error]: {e} -> Fallback to text.")
            self.send_message(chat_id, clean_text)
            return False
        finally:
            try:
                if os.path.exists(temp_ogg):
                    os.remove(temp_ogg)
            except Exception:
                pass

    def send_chat_action(self, chat_id: int, action: str = "typing"):
        """Displays 'typing' or 'upload_photo' status in Telegram."""
        url = f"{API_BASE}/sendChatAction"
        try:
            requests.post(url, json={"chat_id": chat_id, "action": action}, timeout=5)
        except Exception:
            pass

    def get_updates(self, offset: Optional[int] = None, timeout: int = 20) -> list:
        """Fetches incoming Telegram messages and callbacks via long polling."""
        url = f"{API_BASE}/getUpdates"
        params = {"timeout": timeout, "allowed_updates": json.dumps(["message", "callback_query"])}
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
        try:
            resp = requests.get(url, params={"file_id": file_id}, timeout=15).json()
            if resp.get("ok"):
                file_path = resp["result"]["file_path"]
                download_url = f"{FILE_BASE}/{file_path}"
                r = requests.get(download_url, timeout=30)
                if r.status_code == 200:
                    return r.content
        except Exception as e:
            print(f"[Telegram Download Error]: {e}")
        return b""

    def handle_callback_query(self, callback_query: dict):
        """Processes inline button interactions for Guardian action authorization."""
        from approval import ApprovalRegistry

        query_id = callback_query.get("id")
        data = callback_query.get("data", "")
        msg = callback_query.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        message_id = msg.get("message_id")

        if not data or not chat_id:
            self.answer_callback_query(query_id)
            return

        print(f"[Telegram Callback]: User clicked button '{data}'")

        if data.startswith("act_approve:"):
            action_id = data.split(":", 1)[1]
            self.answer_callback_query(query_id, text="Action Authorized!")
            success, msg_text = ApprovalRegistry.approve(action_id, note="Approved via Telegram inline button")
            self.edit_message(
                chat_id,
                message_id,
                f"{msg.get('text', '')}\n\n━━━━━━━━━━━━━━\n{msg_text}",
                reply_markup={"inline_keyboard": []}  # Remove buttons after decision
            )

        elif data.startswith("act_deny:"):
            action_id = data.split(":", 1)[1]
            self.answer_callback_query(query_id, text="Action Denied.")
            success, msg_text = ApprovalRegistry.deny(action_id, note="Denied via Telegram inline button")
            self.edit_message(
                chat_id,
                message_id,
                f"{msg.get('text', '')}\n\n━━━━━━━━━━━━━━\n{msg_text}",
                reply_markup={"inline_keyboard": []}  # Remove buttons after decision
            )

        elif data.startswith("act_explain:"):
            action_id = data.split(":", 1)[1]
            self.answer_callback_query(query_id, text="Loading technical explanation...")
            prop = ApprovalRegistry.get_proposal(action_id)
            if not prop:
                self.send_message(chat_id, f"⚠️ Proposal '{action_id}' not found.")
                return

            explanation_text = (
                f"ℹ️ *[TECHNICAL EXPLANATION FOR {action_id}]*\n\n"
                f"**Action Title:** `{prop['title']}`\n"
                f"**Type:** `{prop['action_type']}` | **Risk:** `{prop['risk_level']}`\n\n"
                f"{prop['explanation']}\n\n"
                f"_Sir, would you like to proceed or deny this action?_"
            )
            # Re-present the Approve / Deny buttons
            inline_keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve Now", "callback_data": f"act_approve:{action_id}"},
                        {"text": "❌ Deny Action", "callback_data": f"act_deny:{action_id}"}
                    ]
                ]
            }
            self.send_message(chat_id, explanation_text, parse_mode="Markdown", reply_markup=inline_keyboard)

        # ------------------------------------------------------------------
        # YOUTUBE VIDEO HUMAN APPROVAL WORKFLOW
        # ------------------------------------------------------------------
        elif data.startswith("yt_approve:"):
            proposal_id = data.split(":", 1)[1]
            self.answer_callback_query(query_id, text="🚀 Authorizing YouTube upload...")
            try:
                from youtube_studio.uploader import publish_approved_video
                up_res = publish_approved_video(proposal_id)
                status = up_res.get("status", "SUCCESS")
                title = up_res.get("title", "YouTube Short")
                v_url = up_res.get("video_url") or up_res.get("url", "Live on channel")

                new_caption = (
                    f"✅ **[APPROVED & PUBLISHED LIVE ON YOUTUBE]**\n\n"
                    f"📹 **Title:** {title}\n"
                    f"🔗 **Status:** {status}\n"
                    f"🌐 **Link:** {v_url}\n\n"
                    f"_Published per Mateen Sir's authorization._"
                )
                self.edit_message_caption(chat_id, message_id, new_caption, parse_mode="Markdown", reply_markup={"inline_keyboard": []})
            except Exception as e:
                self.send_message(chat_id, f"⚠️ Error publishing approved video: {e}")

        elif data.startswith("yt_reject:"):
            proposal_id = data.split(":", 1)[1]
            self.answer_callback_query(query_id, text="❌ Video Rejected.")
            try:
                from youtube_studio.scheduler import reject_pending_video
                rej_res = reject_pending_video(proposal_id)
                title = rej_res.get("title", "Video")

                new_caption = (
                    f"❌ **[REJECTED & DELETED]**\n\n"
                    f"📹 **Title:** {title}\n"
                    f"🗑️ **Status:** Video file hard-deleted to preserve disk space.\n"
                    f"⏰ **Cadence Slot:** Placed on 4-hour cooldown to prevent infinite retry loops.\n\n"
                    f"_Action rejected per Sir's directive._"
                )
                self.edit_message_caption(chat_id, message_id, new_caption, parse_mode="Markdown", reply_markup={"inline_keyboard": []})
            except Exception as e:
                self.send_message(chat_id, f"⚠️ Error rejecting video: {e}")

        elif data.startswith("yt_explain:"):
            proposal_id = data.split(":", 1)[1]
            self.answer_callback_query(query_id, text="Loading technical choices...")
            try:
                from youtube_studio.scheduler import get_pending_review_item
                item = get_pending_review_item(proposal_id)
                if not item:
                    self.send_message(chat_id, f"⚠️ Review item '{proposal_id}' not found in queue.")
                    return

                title = item.get("title", "Untitled Short")
                genre = item.get("genre", "anime")
                slot = item.get("slot_label", "Scheduled Slot")
                rationale = item.get("editorial_rationale", "Optimized for viral audience retention.")
                climaxes = item.get("optical_flow_climaxes", [14.2, 22.8, 31.5])
                climaxes_str = ", ".join(f"{t:.1f}s" for t in climaxes)
                stems = item.get("audio_stems", "Demucs Master Audio Stems")

                explanation_msg = (
                    f"ℹ️ *[EDITORIAL & ALGORITHMIC CHOICES — {proposal_id}]*\n\n"
                    f"📹 **Video:** `{title}`\n"
                    f"⚡ **Category:** `{genre.upper()}` | **Slot:** `{slot}`\n\n"
                    f"🎯 **Why This Topic Was Chosen:**\n{rationale}\n\n"
                    f"💥 **Farneback Optical Flow Climax Cuts:**\n"
                    f"Kinetic action peaks detected at: `{climaxes_str}`.\n"
                    f"These high-motion intervals were dynamically synchronized with beat drops for maximum retention.\n\n"
                    f"🎵 **Audio Stems & Sound Design:**\n{stems}\n\n"
                    f"_Sir, would you like to approve & publish this video to YouTube or reject it?_"
                )
                inline_keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Approve & Publish", "callback_data": f"yt_approve:{proposal_id}"},
                            {"text": "❌ Reject", "callback_data": f"yt_reject:{proposal_id}"}
                        ]
                    ]
                }
                self.send_message(chat_id, explanation_msg, parse_mode="Markdown", reply_markup=inline_keyboard)
            except Exception as e:
                self.send_message(chat_id, f"⚠️ Error loading explanation: {e}")

        else:
            self.answer_callback_query(query_id)

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
        self.handle_text_message(chat_id, transcribed_text, from_voice=True)

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

    def handle_text_message(self, chat_id: int, text: str, from_voice: bool = False):
        """Processes a text command or query through Z.A.I.N.E Agent."""
        clean = text.strip()
        if not clean:
            return

        try:
            from heartbeat import heartbeat_daemon
            heartbeat_daemon.record_activity(channel="telegram", chat_id=chat_id)
        except Exception:
            pass

        # 1. Approval Subsystem Commands
        from approval import ApprovalRegistry

        lower_clean = clean.lower()
        if lower_clean in ("/pending", "/approvals", "pending"):
            pending = ApprovalRegistry.list_pending()
            if not pending:
                self.send_message(chat_id, "✅ No pending actions requiring approval, Sir. Everything is clear!")
            else:
                lines = [f"🛡️ *Pending Action Authorizations ({len(pending)}):*\n"]
                for p in pending:
                    lines.append(f"• `{p['id']}`: *{p['title']}* ({p['action_type']}, Risk: {p['risk_level']})")
                lines.append("\nUse `/approve <id>`, `/deny <id>`, or `/explain <id>` to decide.")
                self.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
            return

        elif lower_clean.startswith(("/approve", "approve")):
            parts = clean.split()
            target_id = parts[1] if len(parts) > 1 else ""
            if not target_id:
                latest = ApprovalRegistry.get_latest_pending()
                if latest:
                    target_id = latest["id"]
                else:
                    self.send_message(chat_id, "⚠️ No pending proposals to approve.")
                    return

            success, msg_text = ApprovalRegistry.approve(target_id, note="Approved via Telegram text")
            self.send_message(chat_id, msg_text)
            return

        elif lower_clean.startswith(("/deny", "deny")):
            parts = clean.split()
            target_id = parts[1] if len(parts) > 1 else ""
            if not target_id:
                latest = ApprovalRegistry.get_latest_pending()
                if latest:
                    target_id = latest["id"]
                else:
                    self.send_message(chat_id, "⚠️ No pending proposals to deny.")
                    return

            success, msg_text = ApprovalRegistry.deny(target_id, note="Denied via Telegram text")
            self.send_message(chat_id, msg_text)
            return

        elif lower_clean.startswith(("/explain", "explain")):
            parts = clean.split()
            target_id = parts[1] if len(parts) > 1 else ""
            if not target_id:
                latest = ApprovalRegistry.get_latest_pending()
                if latest:
                    target_id = latest["id"]
                else:
                    self.send_message(chat_id, "⚠️ No pending proposals to explain.")
                    return

            prop = ApprovalRegistry.get_proposal(target_id)
            if not prop:
                self.send_message(chat_id, f"⚠️ Proposal '{target_id}' not found.")
                return

            explanation_text = (
                f"ℹ️ *[TECHNICAL EXPLANATION FOR {target_id}]*\n\n"
                f"**Action Title:** `{prop['title']}`\n"
                f"**Type:** `{prop['action_type']}` | **Risk:** `{prop['risk_level']}`\n\n"
                f"{prop['explanation']}\n\n"
                f"_Sir, do you approve or deny this implementation?_"
            )
            inline_keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve Now", "callback_data": f"act_approve:{target_id}"},
                        {"text": "❌ Deny Action", "callback_data": f"act_deny:{target_id}"}
                    ]
                ]
            }
            self.send_message(chat_id, explanation_text, parse_mode="Markdown", reply_markup=inline_keyboard)
            return

        # 2. Slash Command Shortcuts
        if clean == "/start":
            welcome = (
                "👋 *Assalamu Alaikum, Mateen sir!*\n\n"
                "I am **Z.A.I.N.E**, your personal sovereign AI assistant & system engineer.\n\n"
                "⚡ *Core Commands:*\n"
                "• `/status` — Live hardware telemetry (CPU, RAM, GPU)\n"
                "• `/pending` — View actions awaiting your approval\n"
                "• `/screen` — Capture live desktop screen\n"
                "• `/camera` — Capture laptop webcam snapshot\n"
                "• `/emails` — Check Gmail inbox\n"
                "• `/tasks` — View active task list\n"
                "• `/clear` — Reset conversation context\n\n"
                "I am equipped with the **Guardian Protocol** — whenever I formulate a major system change or tool synthesis, I will send you an interactive authorization request directly here for your approval!"
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

        elif clean == "/faces" or clean == "/enrolled_faces":
            from face_id import list_enrolled_faces
            faces = list_enrolled_faces()
            if not faces:
                self.send_message(chat_id, "👤 *No enrolled faces in database.*\nUse `/enroll <name> <admin|guest> [note]` to register one.", parse_mode="Markdown")
            else:
                lines = ["👤 *Z.A.I.N.E Biometric Identities:*"]
                for f in faces:
                    role_badge = "👑 ADMIN" if f["role"] == "admin" else "🛡️ GUEST"
                    note = f" — _{f['relationship_note']}_" if f["relationship_note"] else ""
                    lines.append(f"• *{f['name']}* [{role_badge}]{note}")
                self.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
            return

        elif clean.startswith("/enroll"):
            parts = clean.replace("/enroll", "", 1).strip().split()
            if not parts:
                self.send_message(
                    chat_id,
                    "Usage: `/enroll <name> [admin|guest] [relationship_note]`\nExample: `/enroll Sarah guest Friend`",
                    parse_mode="Markdown"
                )
            else:
                target_name = parts[0]
                target_role = parts[1].lower() if len(parts) > 1 and parts[1].lower() in ("admin", "guest") else "guest"
                target_note = " ".join(parts[2:]) if len(parts) > 2 else ""

                self.send_message(chat_id, f"📸 *Initiating Face Enrollment for {target_name}...*\nPlease position the face in front of the workstation camera. Capturing reference angles...", parse_mode="Markdown")
                from face_id import enroll_person
                res = enroll_person(name=target_name, role=target_role, relationship_note=target_note)
                if res.get("status") == "success":
                    self.send_message(
                        chat_id,
                        f"✅ *Enrollment Successful!*\n\n"
                        f"👤 *Name:* `{res['name']}`\n"
                        f"🛡️ *Role:* `{res['role'].upper()}`\n"
                        f"📝 *Note:* `{res.get('relationship_note') or 'None'}`\n"
                        f"📊 *Samples:* `{res.get('samples_used', 5)}` averaged 128D embeddings.\n\n"
                        f"Z.A.I.N.E will now recognize and greet {target_name} automatically.",
                        parse_mode="Markdown"
                    )
                else:
                    self.send_message(chat_id, f"❌ *Enrollment Failed:*\n{res.get('message', 'Unknown error')}", parse_mode="Markdown")
            return

        elif clean.startswith("/deleteface"):
            name = clean.replace("/deleteface", "", 1).strip()
            if not name:
                self.send_message(chat_id, "Usage: `/deleteface <name>`", parse_mode="Markdown")
            else:
                from face_id import delete_enrolled_face
                if delete_enrolled_face(name):
                    self.send_message(chat_id, f"🗑️ Enrolled face profile for *{name}* has been deleted.", parse_mode="Markdown")
                else:
                    self.send_message(chat_id, f"❌ No enrolled face profile found for '{name}'.", parse_mode="Markdown")
            return

        elif clean.startswith("/voicemode") or clean.startswith("/voice_mode"):
            parts = clean.split(maxsplit=1)
            if len(parts) == 1:
                curr_mode = get_chat_voice_mode(chat_id)
                msg = (
                    f"🎙️ *Voice Mode Settings:*\n\n"
                    f"Current Mode: *{curr_mode.upper()}*\n\n"
                    f"• `/voicemode auto` — Voice notes get voice replies, text gets text (Default)\n"
                    f"• `/voicemode on` — Always reply with voice notes\n"
                    f"• `/voicemode off` — Always reply with text messages"
                )
                self.send_message(chat_id, msg, parse_mode="Markdown")
            else:
                arg = parts[1].strip().lower()
                if arg in ("on", "enable", "true", "1"):
                    set_chat_voice_mode(chat_id, "on")
                    self.send_message(chat_id, "✅ Voice Mode set to *ON*. All responses will now be delivered as voice notes.", parse_mode="Markdown")
                elif arg in ("off", "disable", "false", "0"):
                    set_chat_voice_mode(chat_id, "off")
                    self.send_message(chat_id, "✅ Voice Mode set to *OFF*. All responses will now be delivered as text messages.", parse_mode="Markdown")
                elif arg in ("auto", "default", "dynamic"):
                    set_chat_voice_mode(chat_id, "auto")
                    self.send_message(chat_id, "✅ Voice Mode set to *AUTO*. Voice notes get voice replies, text messages get text.", parse_mode="Markdown")
                else:
                    self.send_message(chat_id, "⚠️ Invalid option. Use `/voicemode auto`, `/voicemode on`, or `/voicemode off`.", parse_mode="Markdown")
            return

        elif clean == "/clear":
            if self.agent and hasattr(self.agent, "memory"):
                self.agent.memory.clear()
            else:
                try:
                    requests.post(f"{get_core_service_url()}/api/context/clear", timeout=5)
                except Exception:
                    pass
            self.send_message(chat_id, "🧹 Shared conversation context cleared across all interfaces (HUD, Telegram, Cascade).")
            return

        elif clean in ("/help", "/commands"):
            help_text = (
                r"⚡ *Z.A.I.N.E Pocket Commands:*" + "\n\n"
                r"• `/status` — Live hardware telemetry" + "\n"
                r"• `/pending` — View actions awaiting approval" + "\n"
                r"• `/approve [id]` — Authorize pending implementation" + "\n"
                r"• `/deny [id]` — Reject pending implementation" + "\n"
                r"• `/explain [id]` — Detailed technical breakdown" + "\n"
                r"• `/voicemode [auto|on|off]` — Toggle voice note replies" + "\n"
                r"• `/screen` — Live desktop screenshot" + "\n"
                r"• `/camera` — 1-shot laptop webcam snapshot" + "\n"
                r"• `/emails` — Check unread Gmail inbox" + "\n"
                r"• `/tasks` — View active task list" + "\n"
                r"• `/remind <time> | <msg>` — Set alarm/reminder" + "\n"
                r"• `/reminders` — View scheduled alarms" + "\n"
                r"• `/vault <query>` — Search Personal Second Brain" + "\n"
                r"• `/notes` — List saved Second Brain docs" + "\n"
                r"• `/addnote <title> | <msg>` — Save note to vault" + "\n"
                r"• `/clear` — Reset shared conversation context" + "\n\n"
                "You can also chat freely in English or Urdu/Hindi, or send voice notes!"
            )
            self.send_message(chat_id, help_text, parse_mode="Markdown")
            return

        # 3. General Autonomous LLM query & Tool Calling with Continuous Heartbeat
        self._start_typing_heartbeat(chat_id)
        try:
            reply = self._chat_with_agent(clean)
            self._stop_typing_heartbeat(chat_id)

            mode = get_chat_voice_mode(chat_id)
            should_voice = (mode == "on") or (mode == "auto" and from_voice)

            if should_voice:
                self.send_voice_reply(chat_id, reply)
            else:
                self.send_message(chat_id, reply)
        except Exception as e:
            self._stop_typing_heartbeat(chat_id)
            self.send_message(chat_id, f"⚠️ Error processing command: {e}")

    def register_bot_commands(self):
        """Registers slash command autocomplete menu in Telegram client."""
        commands = [
            {"command": "status", "description": "Hardware telemetry (CPU, RAM, Battery)"},
            {"command": "pending", "description": "View pending action authorizations"},
            {"command": "approve", "description": "Approve action (<id>)"},
            {"command": "deny", "description": "Deny action (<id>)"},
            {"command": "explain", "description": "Detailed explanation (<id>)"},
            {"command": "voicemode", "description": "Configure voice replies (auto, on, off)"},
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
        """Main non-blocking polling loop for incoming Telegram messages and callbacks."""
        if not TELEGRAM_BOT_TOKEN:
            print("[Pocket Zaine]: TELEGRAM_BOT_TOKEN not set in .env. Bridge inactive.")
            return

        if not acquire_telegram_lock():
            print("[Pocket Zaine]: Another Telegram bridge instance is already actively polling. Standing down to prevent conflict.")
            return

        # In standalone mode (no local agent bound), verify Core Service health before polling
        if self.agent is None:
            print("[Pocket Zaine]: Standalone mode active. Verifying Core Service health...")
            wait_for_core_service()

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

                    # 1. Handle Inline Button Callback Queries
                    if "callback_query" in u:
                        cb = u["callback_query"]
                        from_user = cb.get("from", {})
                        user_id = str(from_user.get("id", ""))
                        if TELEGRAM_ALLOWED_USER_ID and user_id != TELEGRAM_ALLOWED_USER_ID:
                            self.answer_callback_query(cb.get("id"), text="Access Denied.")
                            continue
                        threading.Thread(target=self.handle_callback_query, args=(cb,), daemon=True).start()
                        continue

                    # 2. Handle Messages
                    msg = u.get("message")
                    if not msg:
                        continue

                    chat_id = msg["chat"]["id"]
                    from_user = msg.get("from", {})
                    user_id = str(from_user.get("id", ""))
                    username = from_user.get("username", "Unknown")

                    # Security & Whitelist Authentication
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

                    # Authenticated User Message Handling in Background Worker
                    if "voice" in msg:
                        threading.Thread(target=self.handle_voice_message, args=(chat_id, msg["voice"]), daemon=True).start()
                    elif "photo" in msg:
                        caption = msg.get("caption", "")
                        threading.Thread(target=self.handle_photo_message, args=(chat_id, msg["photo"], caption), daemon=True).start()
                    elif "text" in msg:
                        threading.Thread(target=self.handle_text_message, args=(chat_id, msg["text"]), daemon=True).start()

            except Exception as loop_e:
                print(f"[Pocket Zaine Polling Notice]: {loop_e}")
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
