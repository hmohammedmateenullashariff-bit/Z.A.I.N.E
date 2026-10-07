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
import uuid
from typing import Optional, Dict, Tuple, Any
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

# Request Coordinator & Atomic Idempotency Engine
from coordinator import get_request_coordinator

_coordinator = get_request_coordinator()


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

        # 0. Core Service Health Check (/api/health)
        if path == "/api/health":
            port = getattr(self.server.ui_instance, "port", 7860) if hasattr(self.server, "ui_instance") and self.server.ui_instance else 7860
            payload = json.dumps({
                "ok": True,
                "status": "online",
                "port": port,
                "timestamp": time.time()
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 0b. Core Coordinator Queue Telemetry (/api/queue)
        if path == "/api/queue":
            payload = json.dumps(_coordinator.get_queue_telemetry()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 0c. Request Status Check (/api/requests/<id>)
        if path.startswith("/api/requests/"):
            req_id = path[len("/api/requests/"):].strip()
            payload = json.dumps(_coordinator.get_request_status(req_id)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

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
            init_mode = {"type": "mode", "mode": getattr(self.server.ui_instance, "current_mode", "jarvis")}
            init_telem = {"type": "telemetry", "data": _get_system_telemetry()}
            self.wfile.write(f"data: {json.dumps(init_status)}\n\n".encode("utf-8"))
            self.wfile.write(f"data: {json.dumps(init_mode)}\n\n".encode("utf-8"))
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

        # 4b. Ultron Mode Status (/api/mode)
        if path == "/api/mode":
            mode = getattr(self.server.ui_instance, "current_mode", "jarvis")
            payload = json.dumps({"status": "ok", "mode": mode}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 4d. Mute Status (/api/mute)
        if path == "/api/mute":
            try:
                from voice import is_muted
                muted = is_muted()
            except Exception:
                muted = False
            payload = json.dumps({"status": "ok", "muted": muted}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 4e. Conversation Episodes History (/api/history)
        if path == "/api/history":
            try:
                import memory
                conn = memory._get_memory_conn()
                rows = conn.execute(
                    "SELECT id, session_start, session_end, topic_summary, key_points, keywords, created_at FROM conversation_episodes ORDER BY id DESC LIMIT 15"
                ).fetchall()
                conn.close()
                episodes = [
                    {
                        "id": r[0],
                        "session_start": r[1],
                        "session_end": r[2],
                        "topic_summary": r[3],
                        "key_points": r[4],
                        "keywords": r[5],
                        "created_at": r[6]
                    }
                    for r in rows
                ]
            except Exception as e:
                episodes = []
            payload = json.dumps({"status": "ok", "episodes": episodes}).encode("utf-8")
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

        # 6. Workspace File Browser Tree (/api/workspace/tree)
        if path == "/api/workspace/tree":
            query_params = urllib.parse.parse_qs(parsed.query)
            subpath = query_params.get("path", [""])[0].strip()
            try:
                from tools import _resolve_workspace_path, WORKSPACE_DIR
                target = _resolve_workspace_path(subpath) if subpath else WORKSPACE_DIR
                if not target.exists() or not target.is_dir():
                    raise ValueError(f"Folder '{subpath}' does not exist in workspace.")
                items = []
                for item in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                    rel = str(item.relative_to(WORKSPACE_DIR)).replace("\\", "/")
                    is_dir = item.is_dir()
                    size = item.stat().st_size if not is_dir else 0
                    mtime = item.stat().st_mtime
                    ext = item.suffix.lstrip(".").lower() if not is_dir else "folder"
                    items.append({
                        "name": item.name,
                        "path": rel,
                        "is_dir": is_dir,
                        "size": size,
                        "mtime": mtime,
                        "ext": ext,
                    })
                payload = json.dumps({"status": "ok", "path": subpath, "items": items}).encode("utf-8")
            except Exception as e:
                payload = json.dumps({"status": "error", "message": str(e), "items": []}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 7. Workspace File Content Inspector (/api/workspace/file)
        if path == "/api/workspace/file":
            query_params = urllib.parse.parse_qs(parsed.query)
            filepath = query_params.get("path", [""])[0].strip()
            try:
                from tools import _resolve_workspace_path, read_workspace_file, WORKSPACE_DIR
                target = _resolve_workspace_path(filepath)
                if not target.exists() or not target.is_file():
                    raise ValueError(f"File '{filepath}' not found.")
                content = read_workspace_file(filepath)
                payload = json.dumps({
                    "status": "ok",
                    "path": filepath,
                    "name": target.name,
                    "content": content,
                    "size": target.stat().st_size,
                    "mtime": target.stat().st_mtime,
                }).encode("utf-8")
            except Exception as e:
                payload = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 8. Gesture Tracking Status (/api/gesture/status)
        if path == "/api/gesture/status":
            try:
                from gesture_control import is_gesture_tracker_active
                active = is_gesture_tracker_active()
            except Exception:
                active = False
            payload = json.dumps({"status": "ok", "active": active}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # 9. Lock Screen Status (/api/lockscreen/status)
        if path == "/api/lockscreen/status":
            try:
                from face_id import get_active_user
                usr = get_active_user()
            except Exception:
                usr = {"name": "Mateen Sir", "role": "admin"}
            payload = json.dumps({"status": "ok", "user": usr}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        try:
            self._handle_post()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except Exception as e:
            import traceback
            print(f"[HUD do_POST Error]: {e}")
            traceback.print_exc()
            try:
                self.send_error(500, str(e))
            except Exception:
                pass

    def _handle_post(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        print(f"[HUD do_POST]: Received request for {path}")

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        print(f"[HUD do_POST]: Read body length {length}: {body}")
        try:
            req_data = json.loads(body)
        except Exception:
            req_data = {}

        # 1. Ultron Mode Toggle (/api/mode)
        if path == "/api/mode":
            target_mode = req_data.get("mode", "").lower().strip()
            curr = getattr(self.server.ui_instance, "current_mode", "jarvis")
            enable = (target_mode == "ultron") if target_mode else (curr != "ultron")
            from tools import toggle_ultron_mode
            res_str = toggle_ultron_mode(enable)
            active_mode = "ultron" if enable else "jarvis"
            resp_payload = json.dumps({"status": "ok", "mode": active_mode, "message": res_str}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_payload)))
            self.end_headers()
            self.wfile.write(resp_payload)
            return

        # 1b. Mute Toggle / Set (/api/mute)
        if path == "/api/mute":
            try:
                from voice import set_muted, toggle_muted
                if "muted" in req_data:
                    new_state = set_muted(req_data["muted"])
                else:
                    new_state = toggle_muted()
            except Exception:
                new_state = False

            # Broadcast update via SSE to all open HUD windows
            if hasattr(self.server, "ui_instance") and self.server.ui_instance:
                self.server.ui_instance.broadcast({
                    "type": "mute_state",
                    "muted": new_state
                })

            resp_payload = json.dumps({"status": "ok", "muted": new_state}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_payload)))
            self.end_headers()
            self.wfile.write(resp_payload)
            return

        # 2. Chat Transmission (/api/chat)
        if path == "/api/chat":
            user_msg = req_data.get("message", "").strip()
            if not user_msg:
                self.send_error(400, "Message empty")
                return

            client = req_data.get("client", "hud")
            request_id = str(req_data.get("request_id") or uuid.uuid4())

            # Atomic check-and-claim idempotency step under coordinator lock
            claim_status, m_req, cached = _coordinator.claim_request(request_id=request_id, client=client)

            if claim_status == "completed":
                resp_payload = json.dumps(cached).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp_payload)))
                self.end_headers()
                self.wfile.write(resp_payload)
                return

            if claim_status == "in_flight":
                # Duplicate request_id arrived while first is still in-flight
                # Wait for the first request to complete (either completed or failed)
                finished = m_req.wait_for_completion(timeout=120)
                if not finished:
                    self.send_error(504, "In-flight duplicate request timed out")
                    return
                if m_req.state == "failed":
                    err_msg = m_req.error or "In-flight request failed"
                    self.send_error(500, f"Error processing chat: {err_msg}")
                    return
                if m_req.result is not None:
                    resp_payload = json.dumps(m_req.result).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(resp_payload)))
                    self.end_headers()
                    self.wfile.write(resp_payload)
                    return
                else:
                    self.send_error(500, "In-flight duplicate request finished with empty result")
                    return

            # claim_status == "claimed"
            was_queued = False
            waited_seconds = 0.0
            if m_req.state == "queued":
                was_queued = True
                if hasattr(self.server, "ui_instance") and self.server.ui_instance:
                    self.server.ui_instance.set_status("queued")
                # Wait for execution turn
                turn_ok = m_req.wait_for_turn(timeout=120)
                if not turn_ok:
                    _coordinator.fail_request(request_id, "Timed out waiting in queue")
                    self.send_error(504, "Queued request timed out waiting for execution turn")
                    return
                waited_seconds = round(time.time() - m_req.queued_at, 3)

            self.server.ui_instance.set_status("thinking")
            agent = self.server.ui_instance.agent
            tool_called = None
            mode = "jarvis"
            try:
                if agent:
                    reply = agent.chat(user_msg)
                    tool_called = getattr(agent, "last_tool_called", None)
                    mode = "ultron" if getattr(agent, "ultron_mode", False) else "jarvis"
                else:
                    reply = "Agent engine not bound to UI instance."

                resp_dict = {
                    "ok": True,
                    "reply": reply,
                    "tool_called": tool_called,
                    "mode": mode,
                    "request_id": request_id,
                    "queued": was_queued,
                    "waited_seconds": waited_seconds,
                }
                _coordinator.complete_request(request_id, resp_dict)
            except Exception as e:
                _coordinator.fail_request(request_id, str(e))
                self.server.ui_instance.set_status("idle")
                self.send_error(500, f"Error processing chat: {e}")
                return

            self.server.ui_instance.set_status("idle")
            resp_payload = json.dumps(resp_dict).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_payload)))
            self.end_headers()
            self.wfile.write(resp_payload)
            return

        # 2b. Streaming Chat Transmission (/api/chat/stream)
        if path == "/api/chat/stream":
            user_msg = req_data.get("message", "").strip()
            if not user_msg:
                self.send_error(400, "Message empty")
                return

            client = req_data.get("client", "cascade")
            request_id = str(req_data.get("request_id") or uuid.uuid4())

            # Atomic check-and-claim idempotency step under coordinator lock
            claim_status, m_req, cached = _coordinator.claim_request(request_id=request_id, client=client)

            if claim_status == "completed":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(f"data: {json.dumps({'type': 'done', **cached})}\n\n".encode("utf-8"))
                self.wfile.flush()
                self.close_connection = True
                return

            if claim_status == "in_flight":
                # In-flight duplicate: wait for first request to complete without re-executing
                finished = m_req.wait_for_completion(timeout=120)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                if not finished:
                    self.wfile.write(f"data: {json.dumps({'type': 'error', 'message': 'In-flight duplicate request timed out'})}\n\n".encode("utf-8"))
                elif m_req.state == "failed":
                    err_msg = m_req.error or "In-flight request failed"
                    self.wfile.write(f"data: {json.dumps({'type': 'error', 'state': 'failed', 'message': err_msg})}\n\n".encode("utf-8"))
                elif m_req.result is not None:
                    self.wfile.write(f"data: {json.dumps({'type': 'done', **m_req.result})}\n\n".encode("utf-8"))
                else:
                    self.wfile.write(f"data: {json.dumps({'type': 'error', 'message': 'In-flight duplicate request finished with empty result'})}\n\n".encode("utf-8"))
                self.wfile.flush()
                self.close_connection = True
                return

            # claim_status == "claimed": Send SSE headers immediately
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            # If queued, IMMEDIATELY notify client with queued status and position!
            was_queued = False
            waited_seconds = 0.0
            if m_req.state == "queued":
                was_queued = True
                queue_evt = {
                    "type": "queued",
                    "status": "queued",
                    "position": m_req.position,
                    "request_id": request_id,
                }
                self.wfile.write(f"data: {json.dumps(queue_evt)}\n\n".encode("utf-8"))
                self.wfile.flush()
                if hasattr(self.server, "ui_instance") and self.server.ui_instance:
                    self.server.ui_instance.set_status("queued")

                # Wait for execution turn
                turn_ok = m_req.wait_for_turn(timeout=120)
                if not turn_ok:
                    _coordinator.fail_request(request_id, "Timed out waiting in queue")
                    err_payload = json.dumps({"type": "error", "message": "Queued request timed out waiting for execution turn"})
                    self.wfile.write(f"data: {err_payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    self.close_connection = True
                    return
                waited_seconds = round(time.time() - m_req.queued_at, 3)

            # Execution turn arrived: notify client that request is now running
            run_evt = {
                "type": "running",
                "status": "running",
                "request_id": request_id,
                "waited_seconds": waited_seconds if was_queued else 0.0
            }
            self.wfile.write(f"data: {json.dumps(run_evt)}\n\n".encode("utf-8"))
            self.wfile.flush()

            self.server.ui_instance.set_status("thinking")
            agent = self.server.ui_instance.agent
            tool_called = None
            mode = "jarvis"

            if not agent:
                err_payload = json.dumps({"type": "error", "message": "Agent engine not bound to UI instance."})
                self.wfile.write(f"data: {err_payload}\n\n".encode("utf-8"))
                self.wfile.flush()
                _coordinator.fail_request(request_id, "Agent engine not bound to UI instance.")
                self.server.ui_instance.set_status("idle")
                self.close_connection = True
                return

            def on_tool_event(stage: str, tool_name: str, data: Any):
                try:
                    payload_data = data if isinstance(data, (dict, list, int, float, bool)) else str(data)[:2000]
                    event_payload = json.dumps({
                        "type": "tool_event",
                        "stage": stage,
                        "tool": tool_name,
                        "data": payload_data
                    })
                    self.wfile.write(f"data: {event_payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass

            full_reply_parts = []
            try:
                for sentence in agent.chat_stream(user_msg, on_tool_event=on_tool_event):
                    full_reply_parts.append(sentence)
                    chunk_payload = json.dumps({"type": "token", "content": sentence})
                    self.wfile.write(f"data: {chunk_payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                _coordinator.fail_request(request_id, "Client disconnected prematurely")
                self.server.ui_instance.set_status("idle")
                self.close_connection = True
                return
            except Exception as e:
                _coordinator.fail_request(request_id, str(e))
                try:
                    err_payload = json.dumps({"type": "error", "message": str(e)})
                    self.wfile.write(f"data: {err_payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass
                self.server.ui_instance.set_status("idle")
                self.close_connection = True
                return

            tool_called = getattr(agent, "last_tool_called", None)
            mode = "ultron" if getattr(agent, "ultron_mode", False) else "jarvis"
            full_reply = " ".join(full_reply_parts)

            final_dict = {
                "ok": True,
                "reply": full_reply,
                "tool_called": tool_called,
                "mode": mode,
                "request_id": request_id,
                "queued": was_queued,
                "waited_seconds": waited_seconds,
            }
            _coordinator.complete_request(request_id, final_dict)

            try:
                done_payload = json.dumps({"type": "done", **final_dict})
                self.wfile.write(f"data: {done_payload}\n\n".encode("utf-8"))
                self.wfile.flush()
                print(f"[HUD do_POST]: Emitted done event for {request_id}")
            except Exception:
                pass

            self.server.ui_instance.set_status("idle")
            self.close_connection = True
            return

        # 2c. Clear Global Conversation Context Buffer (/api/context/clear)
        # Deliberate Temporary Architecture: Clears the single shared in-memory FIFO buffer
        # across all connected interfaces (HUD, Telegram, Cascade) until Phase 2b multi-session is added.
        if path in ("/api/context/clear", "/api/chat/clear"):
            agent = self.server.ui_instance.agent
            if agent and hasattr(agent, "memory"):
                agent.memory.clear()

            if hasattr(self.server, "ui_instance") and self.server.ui_instance:
                self.server.ui_instance.broadcast({"type": "context_cleared"})

            resp_dict = {
                "ok": True,
                "status": "cleared",
                "message": "Global conversation context buffer cleared across all clients (HUD, Telegram, Cascade)."
            }
            resp_payload = json.dumps(resp_dict).encode("utf-8")
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

            elif action in ("toggle_ultron", "ultron"):
                curr = getattr(self.server.ui_instance, "current_mode", "jarvis")
                enable = (curr != "ultron")
                from tools import toggle_ultron_mode
                reply = toggle_ultron_mode(enable)

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

        # 3. Workspace Move File / Folder (/api/workspace/move)
        if path == "/api/workspace/move":
            src_str = req_data.get("source", "").strip()
            dst_str = req_data.get("destination", "").strip()
            try:
                from tools import _resolve_workspace_path, WORKSPACE_DIR
                if not src_str or not dst_str:
                    raise ValueError("Source and destination paths are required.")

                src = _resolve_workspace_path(src_str)
                dst = _resolve_workspace_path(dst_str)
                if not src.exists():
                    raise ValueError(f"Source item '{src_str}' does not exist.")

                # If destination is a directory, move inside it
                if dst.exists() and dst.is_dir():
                    final_dst = dst / src.name
                else:
                    final_dst = dst

                # Verify sandbox boundary
                if not str(final_dst.resolve()).startswith(str(WORKSPACE_DIR)):
                    raise ValueError("Operation denied: target escapes workspace sandbox.")

                shutil.move(str(src), str(final_dst))
                rel_final = str(final_dst.relative_to(WORKSPACE_DIR)).replace("\\", "/")
                resp_data = {"status": "ok", "message": f"Successfully moved '{src.name}' to '{rel_final}'."}

                # Broadcast update via SSE
                if hasattr(self.server, "ui_instance") and self.server.ui_instance:
                    self.server.ui_instance.broadcast({"type": "workspace_updated"})
            except Exception as e:
                resp_data = {"status": "error", "message": str(e)}

            resp_payload = json.dumps(resp_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_payload)))
            self.end_headers()
            self.wfile.write(resp_payload)
            return

        # 4. Gesture Tracking Toggle (/api/gesture/toggle)
        if path == "/api/gesture/toggle":
            try:
                from gesture_control import toggle_gesture_tracker, is_gesture_tracker_active
                if "active" in req_data:
                    desired = bool(req_data["active"])
                    curr = is_gesture_tracker_active()
                    if desired != curr:
                        new_state = toggle_gesture_tracker()
                    else:
                        new_state = curr
                else:
                    new_state = toggle_gesture_tracker()
            except Exception as e:
                new_state = False

            resp_payload = json.dumps({"status": "ok", "active": new_state}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_payload)))
            self.end_headers()
            self.wfile.write(resp_payload)
            return

        # 5. Lock Screen Biometric Scan (/api/lockscreen/scan)
        if path == "/api/lockscreen/scan":
            try:
                import face_id
                from voice import speak_with_voice

                res = face_id.identify_person(max_retries=2)
                status = res.get("status")
                name = res.get("name", "Unknown")
                role = res.get("role", "unknown")
                note = res.get("relationship_note", "")
                sim = res.get("similarity", 0.0)
                pct = int(round(sim * 100))

                if status == "recognized" and (role == "admin" or "mateen" in name.lower()):
                    face_id.set_active_user(name, "admin", note, status="recognized")
                    speech_msg = "Admin recognized. Privileges provided."
                    threading.Thread(target=speak_with_voice, args=(speech_msg, "jarvis"), daemon=True).start()

                    resp_data = {
                        "status": "ok",
                        "authenticated": True,
                        "role": "admin",
                        "name": name,
                        "confidence": pct,
                        "message": speech_msg,
                        "voice": "jarvis"
                    }
                    if hasattr(self.server, "ui_instance") and self.server.ui_instance:
                        self.server.ui_instance.broadcast({
                            "type": "lockscreen_unlocked",
                            "role": "admin",
                            "name": name,
                            "message": speech_msg
                        })
                elif status in ("recognized", "unknown"):
                    # Guest or unrecognized visitor
                    guest_name = name if status == "recognized" else "Guest"
                    face_id.set_active_user(guest_name, "guest", note, status="guest")
                    speech_msg = "Unknown person detected, probably a guest."
                    threading.Thread(target=speak_with_voice, args=(speech_msg, "ultron"), daemon=True).start()

                    resp_data = {
                        "status": "ok",
                        "authenticated": True,
                        "role": "guest",
                        "name": guest_name,
                        "confidence": pct,
                        "message": speech_msg,
                        "voice": "ultron"
                    }
                    if hasattr(self.server, "ui_instance") and self.server.ui_instance:
                        self.server.ui_instance.broadcast({
                            "type": "lockscreen_unlocked",
                            "role": "guest",
                            "name": guest_name,
                            "message": speech_msg
                        })
                else:
                    # status in ("no_face", "no_camera")
                    resp_data = {
                        "status": "retry",
                        "authenticated": False,
                        "role": "none",
                        "message": "Optical sensor did not detect a clear face. Please center your face."
                    }
            except Exception as e:
                resp_data = {"status": "error", "authenticated": False, "message": str(e)}

            resp_payload = json.dumps(resp_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_payload)))
            self.end_headers()
            self.wfile.write(resp_payload)
            self.wfile.flush()
            return

        # 6. Lock Screen Bypass / Manual Login (/api/lockscreen/bypass)
        if path == "/api/lockscreen/bypass":
            try:
                mode = req_data.get("mode", "guest").lower().strip()
                pin = req_data.get("pin", "").strip()
                from voice import speak_with_voice
                import face_id

                if pin in ("1337", "admin", "mateen") or mode == "admin":
                    face_id.set_active_user("Mateen Sir", "admin", "Creator", status="recognized")
                    speech_msg = "Admin recognized. Privileges provided."
                    threading.Thread(target=speak_with_voice, args=(speech_msg, "jarvis"), daemon=True).start()
                    resp_data = {"status": "ok", "authenticated": True, "role": "admin", "name": "Mateen Sir", "message": speech_msg}
                else:
                    face_id.set_active_user("Guest", "guest", "", status="guest")
                    speech_msg = "Unknown person detected, probably a guest."
                    threading.Thread(target=speak_with_voice, args=(speech_msg, "ultron"), daemon=True).start()
                    resp_data = {"status": "ok", "authenticated": True, "role": "guest", "name": "Guest", "message": speech_msg}

                if hasattr(self.server, "ui_instance") and self.server.ui_instance:
                    self.server.ui_instance.broadcast({
                        "type": "lockscreen_unlocked",
                        "role": resp_data["role"],
                        "name": resp_data["name"],
                        "message": speech_msg
                    })

                resp_payload = json.dumps(resp_data).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp_payload)))
                self.end_headers()
                self.wfile.write(resp_payload)
                self.wfile.flush()
                print(f"[HUD do_POST]: Successfully responded to {path}")
            except Exception as e:
                import traceback
                print(f"[HUD do_POST /api/lockscreen/bypass Error]: {e}")
                traceback.print_exc()
                err_payload = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err_payload)))
                self.end_headers()
                self.wfile.write(err_payload)
                self.wfile.flush()
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
        self.current_mode = "jarvis"
        self.subscribers = []
        self._lock = threading.Lock()
        self.stop_event = threading.Event()
        self.server = None
        self.server_thread = None
        self.telemetry_thread = None

    def set_mode(self, mode: str):
        """Thread-safe update of current persona mode (jarvis, ultron)."""
        clean = mode.lower().strip()
        if clean != self.current_mode:
            self.current_mode = clean
            self.broadcast({"type": "mode", "mode": clean})
            if self.agent and hasattr(self.agent, "set_ultron_mode"):
                self.agent.set_ultron_mode(clean == "ultron")

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
        """Opens the HUD in native Windows 11 Acrylic Electron Window (with Chrome fallback)."""
        url = f"http://127.0.0.1:{self.port}"
        electron_main = BASE_DIR / "electron" / "main.js"

        # 1. Primary: Native Windows 11 Acrylic Electron Shell
        electron_exe = BASE_DIR / "electron" / "node_modules" / "electron" / "dist" / "electron.exe"
        electron_cmd = BASE_DIR / "electron" / "node_modules" / ".bin" / "electron.cmd"
        electron_main = BASE_DIR / "electron" / "main.js"
        npx_bin = shutil.which("npx") or r"C:\Program Files\nodejs\npx.cmd"

        if electron_main.exists():
            if electron_exe.exists():
                cmd = [str(electron_exe), str(electron_main), f"--url={url}"]
                shell_mode = False
            elif electron_cmd.exists():
                cmd = f'"{electron_cmd}" "{electron_main}" --url={url}'
                shell_mode = True
            elif npx_bin:
                cmd = f'"{npx_bin}" electron "{electron_main}" --url={url}'
                shell_mode = True
            else:
                cmd = None

            if cmd:
                try:
                    subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        shell=shell_mode,
                    )
                    print(f"[Z.A.I.N.E HUD]: Launched in Native Windows 11 Acrylic Window via Electron")
                    return
                except Exception as e:
                    print(f"[Z.A.I.N.E HUD]: Electron launch notice: {e}. Falling back to browser app mode.")

        # --- LEGACY FALLBACK: Chrome / Edge App Mode ---
        # exe = self._find_browser_app_executable()
        # if exe:
        #     try:
        #         subprocess.Popen(
        #             [
        #                 exe,
        #                 f"--app={url}",
        #                 "--window-size=1260,840",
        #                 "--window-position=120,60",
        #             ],
        #             stdout=subprocess.DEVNULL,
        #             stderr=subprocess.DEVNULL,
        #         )
        #         print(f"[Z.A.I.N.E HUD]: Launched in Desktop Application Window via {os.path.basename(exe)}")
        #         return
        #     except Exception as e:
        #         print(f"[Z.A.I.N.E HUD]: App mode launch notice: {e}")

        # Fallback to default browser
        import webbrowser
        webbrowser.open(url)
        print(f"[Z.A.I.N.E HUD]: Opened in default browser at {url}")

    def _write_core_info(self, status: str = "online"):
        """Persists core service connection metadata (.zaine_core.json) for thin clients."""
        try:
            core_file = BASE_DIR / ".zaine_core.json"
            data = {
                "port": self.port,
                "pid": os.getpid(),
                "status": status,
                "updated_at": time.time()
            }
            core_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[ZaineUI Core Discovery Notice]: {e}")

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

        self._write_core_info(status="online")
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
        self._write_core_info(status="offline")
        if self.server:
            try:
                self.server.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    print("Testing Z.A.I.N.E Holographic Jarvis Web HUD...")
    ui = ZaineUI()
    ui.start()
