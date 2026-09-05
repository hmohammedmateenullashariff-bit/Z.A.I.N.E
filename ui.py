"""
Z.A.I.N.E — Holographic Jarvis Web HUD & State Engine (Phase 5 Upgraded)
Hosts a local, high-performance 60FPS Cyberpunk / Jarvis HUD on http://127.0.0.1:7860.
Launches seamlessly in Edge/Chrome Desktop App Mode (--app=http://127.0.0.1:7860).

Features:
- Server-Sent Events (SSE) for zero-latency status, dialogue, and telemetry streaming
- 60FPS Reactive Arc Reactor & Live Audio Waveform Canvas
- Hardware Telemetry Matrix (CPU, RAM, Battery, Storage, Neural Clusters)
- Multimodal Vision Inspector (In-memory screen & camera preview)
- Bidirectional chat & quick actions dock
"""

import os
import json
import time
import queue
import shutil
import psutil
import datetime
import threading
import subprocess
import urllib.parse
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

BASE_DIR = Path(__file__).parent.resolve()
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

DEFAULT_PORT = 7860

# In-memory RAM caches for visual captures
_screen_cache = b""
_camera_cache = b""
_latest_vision_meta = {"caption": "", "type": "SCREEN", "timestamp": 0}


def _get_system_telemetry() -> dict:
    """Collects real-time hardware telemetry for the HUD."""
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent

    battery_info = psutil.sensors_battery()
    bat_pct = int(battery_info.percent) if battery_info else 100
    bat_plugged = bool(battery_info.power_plugged) if battery_info else True

    disk_free = 0
    try:
        _, _, free = shutil.disk_usage("C:\\")
        disk_free = round(free / (1024 ** 3), 1)
    except Exception:
        pass

    hour = datetime.datetime.now().hour
    night_mode = 0 <= hour < 7

    temp_c = None
    try:
        from thermal_guard import get_cpu_temperature_celsius
        temp_c = get_cpu_temperature_celsius()
    except Exception:
        pass

    return {
        "cpu": cpu,
        "ram": ram,
        "temperature": temp_c,
        "battery": bat_pct,
        "battery_plugged": bat_plugged,
        "disk_free": disk_free,
        "night_mode": night_mode,
        "timestamp": time.time(),
    }


class HUDRequestHandler(BaseHTTPRequestHandler):
    """Handles static assets, REST actions, and SSE streaming for the HUD."""

    def log_message(self, format, *args):
        """Suppress noisy request logging in console."""
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. Root: Serve index.html
        if path == "/" or path == "/index.html":
            index_file = TEMPLATES_DIR / "index.html"
            if index_file.exists():
                content = index_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "index.html not found")
            return

        # 2. Static Assets (/static/css/*, /static/js/*)
        if path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            file_path = STATIC_DIR / rel_path
            if file_path.exists() and file_path.is_file():
                mime = "text/plain"
                if file_path.suffix == ".css":
                    mime = "text/css"
                elif file_path.suffix == ".js":
                    mime = "application/javascript"
                elif file_path.suffix in (".png", ".jpg", ".jpeg"):
                    mime = f"image/{file_path.suffix.replace('.', '')}"
                elif file_path.suffix == ".svg":
                    mime = "image/svg+xml"

                content = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, f"Static file {rel_path} not found")
            return

        # 3. Server-Sent Events (/api/stream)
        if path == "/api/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            q = self.server.ui_instance.subscribe()

            # Push initial state & telemetry upon connection
            init_status = {"type": "status", "status": self.server.ui_instance.current_status}
            init_telem = {"type": "telemetry", "data": _get_system_telemetry()}
            self.wfile.write(f"data: {json.dumps(init_status)}\n\n".encode("utf-8"))
            self.wfile.write(f"data: {json.dumps(init_telem)}\n\n".encode("utf-8"))
            self.wfile.flush()

            try:
                while not self.server.ui_instance.stop_event.is_set():
                    try:
                        event_data = q.get(timeout=1.0)
                        msg = f"data: {json.dumps(event_data)}\n\n"
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        # Keep-alive heartbeat comment
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError):
                pass
            finally:
                self.server.ui_instance.unsubscribe(q)
            return

        # 4. Status endpoint (/api/status)
        if path == "/api/status":
            telem = _get_system_telemetry()
            telem["status"] = self.server.ui_instance.current_status
            payload = json.dumps(telem).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 4b. AI Daily Intel endpoint (/api/ai_intel)
        if path == "/api/ai_intel":
            try:
                from ai_daily_intel import get_daily_ai_updates
                updates = get_daily_ai_updates(force_refresh=False)
            except Exception:
                updates = []
            payload = json.dumps({"status": "ok", "updates": updates}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 4c. Overnight Evolution Status endpoint (/api/evolution_status)
        if path == "/api/evolution_status":
            try:
                import home_ops
                import thermal_guard
                data = {
                    "db": home_ops.check_database_health(),
                    "telemetry": home_ops.get_system_telemetry(),
                    "thermal": thermal_guard.get_thermal_telemetry()
                }
            except Exception:
                data = {}
            payload = json.dumps({"status": "ok", "data": data}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 5. Snapshots (/api/snapshot/screen and /api/snapshot/camera)
        if path == "/api/snapshot/screen":
            global _screen_cache
            if not _screen_cache:
                try:
                    from vision import capture_screen_bytes
                    _screen_cache = capture_screen_bytes()
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(_screen_cache)))
            self.end_headers()
            self.wfile.write(_screen_cache)
            return

        if path == "/api/snapshot/camera":
            global _camera_cache
            if not _camera_cache:
                try:
                    from vision import capture_webcam_bytes
                    _camera_cache = capture_webcam_bytes()
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(_camera_cache)))
            self.end_headers()
            self.wfile.write(_camera_cache)
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            req_data = json.loads(body)
        except Exception:
            req_data = {}

        # 1. Chat Transmission (/api/chat)
        if path == "/api/chat":
            user_msg = req_data.get("message", "").strip()
            if not user_msg:
                self.send_error(400, "Message empty")
                return

            self.server.ui_instance.set_status("thinking")
            agent = self.server.ui_instance.agent
            tool_called = None
            if agent:
                reply = agent.chat(user_msg)
                tool_called = getattr(agent, "last_tool_called", None)
            else:
                reply = "Agent engine not bound to UI instance."

            self.server.ui_instance.set_status("idle")
            resp_payload = json.dumps({"reply": reply, "tool_called": tool_called}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_payload)))
            self.end_headers()
            self.wfile.write(resp_payload)
            return

        # 2. Quick Action Trigger (/api/action)
        if path == "/api/action":
            action = req_data.get("action", "").lower().strip()
            reply = ""
            vision_obj = None

            global _screen_cache, _camera_cache, _latest_vision_meta
            if action == "screen":
                try:
                    from vision import capture_screen_bytes, see_screen
                    _screen_cache = capture_screen_bytes()
                    reply = see_screen("Describe what is shown on this screen concisely in 2 sentences.")
                    vision_obj = {
                        "url": "/api/snapshot/screen",
                        "caption": reply,
                        "type": "DESKTOP SCREEN",
                    }
                    self.server.ui_instance.broadcast({
                        "type": "vision",
                        "image_url": "/api/snapshot/screen",
                        "caption": reply,
                        "capture_type": "DESKTOP SCREEN",
                    })
                except Exception as e:
                    reply = f"Error inspecting screen: {e}"

            elif action == "camera":
                try:
                    from vision import capture_webcam_bytes, see_camera
                    _camera_cache = capture_webcam_bytes()
                    reply = see_camera("Describe what you see in front of the camera in 2 sentences.")
                    vision_obj = {
                        "url": "/api/snapshot/camera",
                        "caption": reply,
                        "type": "1-SHOT WEBCAM",
                    }
                    self.server.ui_instance.broadcast({
                        "type": "vision",
                        "image_url": "/api/snapshot/camera",
                        "caption": reply,
                        "capture_type": "1-SHOT WEBCAM",
                    })
                except Exception as e:
                    reply = f"Error accessing camera: {e}"

            elif action == "vault":
                try:
                    from vault import list_vault_documents
                    reply = list_vault_documents()
                except Exception as e:
                    reply = f"Error querying vault: {e}"

            elif action == "emails":
                try:
                    from email_client import check_emails
                    reply = check_emails(unread_only=True, limit=5)
                except Exception as e:
                    reply = f"Error checking emails: {e}"

            elif action == "reminders":
                try:
                    from tools import list_reminders
                    reply = list_reminders()
                except Exception as e:
                    reply = f"Error listing reminders: {e}"

            elif action == "status":
                try:
                    from tools import system_status
                    reply = system_status()
                except Exception as e:
                    reply = f"Error getting status: {e}"

            elif action == "night_mode":
                telem = _get_system_telemetry()
                reply = f"Night Mode is {'Active (Whisper-Quiet)' if telem['night_mode'] else 'Disabled (Daytime Normal)'}."

            else:
                reply = f"Unknown action '{action}'."

            resp_payload = json.dumps({"reply": reply, "vision": vision_obj}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_payload)))
            self.end_headers()
            self.wfile.write(resp_payload)
            return

        self.send_error(404, "Endpoint not found")


_ACTIVE_UI = None


def get_ui():
    """Returns the currently active ZaineUI instance if initialized."""
    global _ACTIVE_UI
    return _ACTIVE_UI


class ZaineUI:
    """
    Manages the Holographic Jarvis Web HUD server, SSE broadcasts,
    and desktop application window launch.
    """

    def __init__(self, agent=None, port: int = DEFAULT_PORT):
        global _ACTIVE_UI
        _ACTIVE_UI = self
        self.agent = agent
        self.port = port
        self.current_status = "idle"
        self.subscribers = []
        self._lock = threading.Lock()
        self.stop_event = threading.Event()
        self.server = None
        self.server_thread = None
        self.telemetry_thread = None


    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=64)
        with self._lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def broadcast(self, data: dict):
        with self._lock:
            for q in list(self.subscribers):
                try:
                    q.put_nowait(data)
                except queue.Full:
                    pass

    def set_status(self, status: str):
        """Thread-safe update of current status (idle, listening, thinking, speaking)."""
        clean = status.lower().strip()
        if clean != self.current_status:
            self.current_status = clean
            self.broadcast({"type": "status", "status": clean})

    def append_message(self, role: str, text: str, tool: str = None):
        """Appends a dialogue turn into the HUD stream."""
        self.broadcast({"type": "message", "role": role, "text": text, "tool": tool})

    def show_vision(self, image_url: str, caption: str, capture_type: str = "DESKTOP SCREEN"):
        """Displays visual snapshot in the HUD vision drawer."""
        self.broadcast({
            "type": "vision",
            "image_url": image_url,
            "caption": caption,
            "capture_type": capture_type,
        })

    def _telemetry_loop(self):
        """Periodically pushes hardware telemetry to all connected HUD clients."""
        while not self.stop_event.is_set():
            telem = _get_system_telemetry()
            self.broadcast({"type": "telemetry", "data": telem})
            for _ in range(4):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

    def _find_browser_app_executable(self) -> str:
        """Finds Edge or Chrome executable on Windows to launch in borderless App Mode."""
        candidates = [
            shutil.which("msedge"),
            shutil.which("chrome"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return ""

    def launch_window(self):
        """Opens the HUD in standalone desktop application mode."""
        url = f"http://127.0.0.1:{self.port}"
        exe = self._find_browser_app_executable()
        if exe:
            try:
                subprocess.Popen(
                    [
                        exe,
                        f"--app={url}",
                        "--window-size=1260,840",
                        "--window-position=120,60",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"[Z.A.I.N.E HUD]: Launched in Desktop Application Window via {os.path.basename(exe)}")
                return
            except Exception as e:
                print(f"[Z.A.I.N.E HUD]: App mode launch notice: {e}")

        # Fallback to default browser
        import webbrowser
        webbrowser.open(url)
        print(f"[Z.A.I.N.E HUD]: Opened in default browser at {url}")

    def start_server(self):
        """Starts the multi-threaded HTTP server."""
        for p in range(self.port, self.port + 10):
            try:
                self.server = ThreadingHTTPServer(("127.0.0.1", p), HUDRequestHandler)
                self.server.ui_instance = self
                self.port = p
                break
            except OSError:
                continue

        if not self.server:
            raise RuntimeError(f"Could not bind HUD server on ports {self.port} to {self.port + 10}")

        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            name="ZaineHUDServer",
            daemon=True,
        )
        self.server_thread.start()

        self.telemetry_thread = threading.Thread(
            target=self._telemetry_loop,
            name="ZaineHUDTelemetry",
            daemon=True,
        )
        self.telemetry_thread.start()

        print(f"\n[Z.A.I.N.E HUD Online]: http://127.0.0.1:{self.port}")

    def start(self):
        """Starts the server, launches the desktop window, and runs the loop."""
        self.start_server()
        self.launch_window()
        # Keep main thread responsive to keyboard interrupts
        try:
            while not self.stop_event.is_set():
                time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit):
            self.stop()

    def stop(self):
        self.stop_event.set()
        if self.server:
            try:
                self.server.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    print("Testing Z.A.I.N.E Holographic Jarvis Web HUD...")
    ui = ZaineUI()
    ui.start()
