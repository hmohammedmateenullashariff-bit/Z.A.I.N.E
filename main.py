"""
Z.A.I.N.E Agent v1 — Main Entry (Wake Word + Visual Screen)

- Say "Zaine" out loud to wake it up, then speak your command.
- After it responds, it listens again for 10 seconds without needing the wake
  word — say something and it keeps going; stay silent and it drops back to idle.
- Or just type in this console at any time — both work together.
- Type 'exit' or 'quit' in the console to stop.

A small screen window opens showing Z.A.I.N.E's current state:
idle / listening / thinking / speaking.
"""

import os
import sys
import time
import threading
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

from colorama import init, Fore, Style
from agent import ZaineAgent
from voice import listen, speak_sentence
from wakeword import wait_for_wake_word
from ui import ZaineUI
from heartbeat import heartbeat_daemon

init(autoreset=True)  # makes ANSI colors work correctly on Windows terminals
ZAINE_NAME = f"{Fore.RED}{Style.BRIGHT}Z.A.I.N.E{Style.RESET_ALL}"

FOLLOW_UP_SECONDS = 10  # how long to keep listening after a response before going idle

agent = ZaineAgent()
ui = ZaineUI(agent=agent)
_lock = threading.Lock()  # prevents voice and typed input from talking to the agent at the same time


def handle_message(user_text: str, source: str = "text") -> bool:
    clean_text = user_text.strip()
    if not clean_text:
        return False

    # 1. Check for voice/text shutdown intent
    lower_check = clean_text.lower().strip()
    if lower_check in ("exit", "quit", "shutdown", "shut down", "power down", "goodbye zaine", "bye zaine") or "shut down" in lower_check and len(clean_text) < 25:
        print(f"\nYou ({source}): {clean_text}")
        print(f"{ZAINE_NAME}: Shutting down systems. Goodbye, Sir.\n")
        try:
            speak_sentence("Shutting down systems. Goodbye, Sir.")
        except Exception:
            pass
        os._exit(0)

    # 2. Check for explicit "go idle / sleep / quiet" intent
    idle_triggers = ["go idle", "go to sleep", "sleep", "be quiet", "stop listening", "stand down", "rest", "don't respond", "dont respond", "quiet"]
    if any(phrase in lower_check for phrase in idle_triggers):
        print(f"\nYou ({source}): {clean_text}")
        ack = "Understood, Sir. Going idle now. Say my name when you need me."
        print(f"{ZAINE_NAME}: {ack}\n")
        try:
            speak_sentence(ack)
        except Exception:
            pass
        ui.set_status("idle")
        return False  # Immediately skip follow-up and wait for wake word

    # 3. Process normal or tool message
    heartbeat_daemon.record_activity()
    with _lock:
        print(f"\nYou ({source}): {clean_text}")
        ui.append_message("user", clean_text)
        ui.set_status("thinking")
        print(f"{ZAINE_NAME}: ", end="", flush=True)

        first_sentence = True
        interrupted = False
        full_assistant_reply = []
        for sentence in agent.chat_stream(clean_text):
            if first_sentence:
                ui.set_status("speaking")
                first_sentence = False
            print(f"{sentence}", end=" ", flush=True)
            full_assistant_reply.append(sentence)
            completed = speak_sentence(sentence, allow_barge_in=(source == "voice"))
            if not completed:
                print(f"\n[{Fore.YELLOW}Barge-In: Speech interrupted by user{Style.RESET_ALL}]")
                interrupted = True
                break

        print("\n")
        if full_assistant_reply:
            ui.append_message(
                "assistant",
                " ".join(full_assistant_reply),
                tool=getattr(agent, "last_tool_called", None)
            )

        if interrupted:
            ui.set_status("idle")
            return False

    # 4. If a media or playback tool was called, immediately go idle so we don't listen to the music
    if getattr(agent, "last_tool_called", None) in ("play_on_youtube", "media_control"):
        print("[Media playing: Dropping to idle to prevent audio interference. Say 'Zaine' to wake]\n")
        ui.set_status("idle")
        return False

    return True


def voice_loop():
    while True:
        # 1. Idle, waiting for the wake word
        ui.set_status("idle")
        wait_for_wake_word("zaine")

        # 2. Wake word heard -> check identity (cached if session is fresh < 5m)
        try:
            from face_id import check_and_greet
            ident = check_and_greet()
            if ident.get("status") == "recognized":
                print(f"\n[Face-ID Verified]: {ident['name']} ({ident['role'].upper()})")
            elif ident.get("status") == "unknown":
                print(f"\n[Face-ID Alert]: Unrecognized visitor -> Operating in Guest Mode")
        except Exception:
            pass

        # 3. Listen for the actual command
        ui.set_status("listening")
        user_text = listen()

        # 3. Keep cycling: respond, then listen again for a follow-up (no wake word needed)
        while user_text.strip():
            should_follow_up = handle_message(user_text, source="voice")
            if not should_follow_up:
                break
            ui.set_status("listening")
            user_text = listen(duration=FOLLOW_UP_SECONDS)

        # 4. Nothing said in the follow-up window -> drop back to idle / wake-word waiting
        print("[Going idle, waiting for wake word]\n")


def text_loop():
    print(f"{ZAINE_NAME} is online. Say 'Zaine' or type here. (type 'exit' to quit)\n")
    while True:
        try:
            user_text = input().strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{ZAINE_NAME}: Shutting down. Bye!")
            os._exit(0)

        if user_text.lower() in ("exit", "quit"):
            print(f"{ZAINE_NAME}: Bye!")
            os._exit(0)

        if user_text.startswith("/"):
            try:
                from terminal_ui import handle_slash_command
                handle_slash_command(user_text)
                continue
            except Exception:
                pass

        if user_text:
            handle_message(user_text, source="text")
            ui.set_status("idle")


if __name__ == "__main__":
    # 1. Start Core HTTP Service Server
    print("[Z.A.I.N.E Core]: Starting multi-threaded HTTP server...")
    ui.start_server()

    # 2. Health-check Gate: Poll GET /api/health until confirmed listening (up to 15s bounded window)
    health_url = f"http://127.0.0.1:{ui.port}/api/health"
    healthy = False
    max_attempts = 50
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(health_url, timeout=1.0)
            if resp.status_code == 200 and resp.json().get("ok"):
                healthy = True
                print(f"[Z.A.I.N.E Core]: HTTP server verified healthy and listening on port {ui.port} (attempt {attempt}).")
                break
        except Exception:
            time.sleep(0.3)

    if not healthy:
        err_msg = f"[FATAL]: Core HTTP server failed to respond healthy on {health_url} after {max_attempts * 0.3:.1f}s. Halting startup to prevent split-brain state."
        print(err_msg)
        ui.stop()
        raise RuntimeError(err_msg)

    # 3. Start Telegram Bridge in background if configured in .env
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if telegram_token:
        try:
            from telegram_bridge import TelegramBridge
            bridge = TelegramBridge()
            threading.Thread(target=bridge.run_polling, daemon=True).start()
            print("[Pocket Zaine]: Telegram background bridge activated.")
        except Exception as e:
            print(f"[Pocket Zaine]: Failed to start Telegram bridge: {e}")

    # 4. Start Proactive Heartbeat Daemon in background
    heartbeat_daemon.start()

    # 5. Start Voice and Text interaction loops
    threading.Thread(target=voice_loop, daemon=True).start()
    threading.Thread(target=text_loop, daemon=True).start()

    # 6. Launch Desktop Window / HUD interface
    ui.launch_window()

    # Keep main thread alive
    try:
        while not ui.stop_event.is_set():
            time.sleep(0.5)
    except (KeyboardInterrupt, SystemExit):
        ui.stop()
