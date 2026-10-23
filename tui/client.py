"""
Z.A.I.N.E TUI Core Service SSE Streaming Client
Handles communication with CoreService (:7860) over REST and Server-Sent Events (SSE).
Features tier-aware timeouts, idle gap detection, and cancellation.
"""

import os
import sys
import json
import time
import uuid
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, AsyncIterator, Tuple
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class StreamTimeoutError(Exception):
    """Raised when first token or idle gap timeout is exceeded."""
    pass


class StreamCancelledError(Exception):
    """Raised when streaming is cancelled by operator."""
    pass


def get_core_service_url() -> str:
    """
    Detects the active CoreService base URL.
    Checks .zaine_core.json, environment variables, or defaults to port 7860.
    """
    # 1. Check .zaine_core.json
    core_info_file = PROJECT_ROOT / ".zaine_core.json"
    if core_info_file.exists():
        try:
            data = json.loads(core_info_file.read_text(encoding="utf-8"))
            port = data.get("port")
            status = data.get("status", "online")
            if port and isinstance(port, int) and status != "offline":
                return f"http://127.0.0.1:{port}"
        except Exception:
            pass

    # 2. Check environment variable
    env_port = os.environ.get("ZAINE_CORE_PORT") or os.environ.get("CORE_PORT")
    if env_port:
        try:
            return f"http://127.0.0.1:{int(env_port)}"
        except ValueError:
            pass

    # 3. Default to standard CoreService port
    return "http://127.0.0.1:7860"


def get_core_service_token() -> str:
    """Retrieves session auth token from environment or .zaine_core.json."""
    env_token = os.environ.get("ZAINE_AUTH_TOKEN")
    if env_token:
        return env_token
    core_info_file = PROJECT_ROOT / ".zaine_core.json"
    if core_info_file.exists():
        try:
            data = json.loads(core_info_file.read_text(encoding="utf-8"))
            return data.get("auth_token", "")
        except Exception:
            pass
    return ""


def get_auth_headers() -> Dict[str, str]:
    """Generates X-Zaine-Token header dict for authenticating with CoreService."""
    tok = get_core_service_token()
    return {"X-Zaine-Token": tok} if tok else {}


async def check_backend_health(base_url: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
    """Checks if CoreService is reachable and online."""
    url = (base_url or get_core_service_url()) + "/api/health"
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return bool(data.get("ok")), data
    except Exception:
        pass
    return False, {}


async def stream_chat_events(
    message: str,
    base_url: Optional[str] = None,
    client_id: str = "terminal-ui",
    request_id: Optional[str] = None,
    default_first_token_timeout: float = 60.0,
    idle_gap_timeout: float = 20.0,
    client: Optional[httpx.AsyncClient] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Streams SSE events from CoreService POST /api/chat/stream.
    Enforces liveness-based silence timeouts, 120s total ceiling, and auto-cancellation.
    """
    root_url = base_url or get_core_service_url()
    stream_url = f"{root_url}/api/chat/stream"
    req_id = request_id or f"term-{uuid.uuid4().hex[:8]}"
    payload = {
        "message": message,
        "client": client_id,
        "request_id": req_id,
    }

    first_token_timeout = default_first_token_timeout
    has_received_token = False
    stream_start_time = time.monotonic()
    last_progress_time = stream_start_time
    total_ceiling_cfg = float(os.getenv("ZAINE_STREAM_CEILING", "300.0"))

    close_client_at_exit = False
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
        )
        close_client_at_exit = True

    try:
        try:
            headers = get_auth_headers()
            async with client.stream("POST", stream_url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    yield {
                        "type": "error",
                        "message": f"HTTP {response.status_code}: {err_body.decode('utf-8', errors='replace')}",
                    }
                    return

                line_iterator = response.aiter_lines()
                is_approval_pending = False
                last_progress_time = time.monotonic()

                while True:
                    # Enforce configurable total stream ceiling (default 300s)
                    elapsed_total = time.monotonic() - stream_start_time
                    remaining_ceiling = max(0.0, total_ceiling_cfg - elapsed_total)
                    if remaining_ceiling <= 0:
                        try:
                            await cancel_chat_request(req_id, base_url=root_url)
                        except Exception:
                            pass
                        raise StreamTimeoutError(f"Total stream timeout ceiling ({total_ceiling_cfg:.0f}s) exceeded.")

                    # Calculate remaining silence until idle gap timeout
                    elapsed_since_progress = time.monotonic() - last_progress_time
                    silence_limit = idle_gap_timeout if has_received_token else first_token_timeout
                    remaining_silence = max(0.0, silence_limit - elapsed_since_progress)
                    if remaining_silence <= 0 and not is_approval_pending:
                        try:
                            await cancel_chat_request(req_id, base_url=root_url)
                        except Exception:
                            pass
                        timeout_kind = "Idle gap" if has_received_token else "Silence (first token)"
                        raise StreamTimeoutError(
                            f"{timeout_kind} timeout ({silence_limit:.0f}s) exceeded while awaiting response."
                        )

                    if is_approval_pending:
                        current_timeout = remaining_ceiling
                    else:
                        current_timeout = min(remaining_silence, remaining_ceiling)

                    try:
                        line = await asyncio.wait_for(anext(line_iterator), timeout=current_timeout)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        try:
                            await cancel_chat_request(req_id, base_url=root_url)
                        except Exception:
                            pass
                        timeout_kind = "Idle gap" if has_received_token else "Silence (first token)"
                        raise StreamTimeoutError(
                            f"{timeout_kind} timeout ({silence_limit:.0f}s) exceeded while awaiting response."
                        )
                    except asyncio.CancelledError:
                        try:
                            await cancel_chat_request(req_id, base_url=root_url)
                        except Exception:
                            pass
                        raise StreamCancelledError("Stream aborted by user.")

                    if not line:
                        continue
                    line_str = line.strip()

                    # Handle heartbeat comments (: ping, : comment)
                    # Before first token, pings count as liveness.
                    # After first token, pings must NOT reset the progress timer unless waiting for approval.
                    if line_str.startswith(":"):
                        if not has_received_token or is_approval_pending:
                            last_progress_time = time.monotonic()
                        continue

                    if not line_str.startswith("data: "):
                        continue

                    raw_json = line_str[6:].strip()
                    try:
                        event = json.loads(raw_json)
                    except Exception:
                        continue

                    ev_type = event.get("type")

                    # Adapt timeout if model route indicates deep reasoning or coder
                    if ev_type == "tool_event":
                        stage = event.get("stage")
                        if stage == "route":
                            route_data = event.get("data")
                            if isinstance(route_data, dict):
                                tier = route_data.get("tier", "")
                                if tier in ("DEEP_REASONING", "DEEP_CODE"):
                                    first_token_timeout = 45.0
                        elif stage == "approval_required":
                            is_approval_pending = True
                            last_progress_time = time.monotonic()
                        elif stage in ("approval_wait",):
                            is_approval_pending = True
                            last_progress_time = time.monotonic()
                        elif stage in ("done", "approved", "denied"):
                            is_approval_pending = False
                            last_progress_time = time.monotonic()

                    # Progress tracking:
                    # After first token, ONLY token or tool_event count as progress.
                    # Before first token, any event (including heartbeats/loading) counts.
                    if ev_type == "token":
                        has_received_token = True
                        is_approval_pending = False
                        last_progress_time = time.monotonic()
                    elif ev_type == "tool_event":
                        if event.get("stage") not in ("approval_required", "approval_wait"):
                            is_approval_pending = False
                        last_progress_time = time.monotonic()
                    elif not has_received_token or is_approval_pending:
                        last_progress_time = time.monotonic()

                    yield event

                    if ev_type in ("done", "error"):
                        break

        except GeneratorExit:
            return
        except httpx.ConnectError:
            yield {
                "type": "error",
                "message": f"Connection refused to Core Service at {stream_url}. Ensure service is running.",
            }
        except httpx.HTTPError as he:
            yield {
                "type": "error",
                "message": f"HTTP transport error: {str(he)}",
            }
    finally:
        if close_client_at_exit:
            await client.aclose()


# --- REST API Convenience Helpers ---

async def clear_context(base_url: Optional[str] = None) -> Dict[str, Any]:
    """Calls POST /api/context/clear to reset short-term memory context."""
    url = (base_url or get_core_service_url()) + "/api/context/clear"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={}, headers=get_auth_headers())
            return resp.json() if resp.status_code == 200 else {"status": "error", "message": resp.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def get_system_status(base_url: Optional[str] = None) -> Dict[str, Any]:
    """Calls GET /api/status for live telemetry, model, and mode."""
    url = (base_url or get_core_service_url()) + "/api/status"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=get_auth_headers())
            return resp.json() if resp.status_code == 200 else {"status": "error", "message": resp.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def set_persona_mode(base_url: Optional[str] = None, mode: Optional[str] = None) -> Dict[str, Any]:
    """Calls POST /api/mode to switch between Jarvis and Ultron personas."""
    url = (base_url or get_core_service_url()) + "/api/mode"
    try:
        payload = {"mode": mode} if mode else {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=get_auth_headers())
            return resp.json() if resp.status_code == 200 else {"status": "error", "message": resp.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def toggle_voice(base_url: Optional[str] = None, enable: Optional[bool] = None) -> Dict[str, Any]:
    """Calls POST /api/voice/toggle to enable/disable speech synthesis."""
    url = (base_url or get_core_service_url()) + "/api/voice/toggle"
    try:
        payload = {"enable": enable} if enable is not None else {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=get_auth_headers())
            return resp.json() if resp.status_code == 200 else {"status": "error", "message": resp.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def get_conversation_history(base_url: Optional[str] = None) -> Dict[str, Any]:
    """Calls GET /api/history to retrieve episodic memory records."""
    url = (base_url or get_core_service_url()) + "/api/history"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url, headers=get_auth_headers())
            return resp.json() if resp.status_code == 200 else {"status": "error", "episodes": []}
    except Exception as e:
        return {"status": "error", "message": str(e), "episodes": []}


async def respond_to_approval(
    proposal_id: str,
    decision: str,
    note: str = "",
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Posts user approval or denial decision to /api/approval/respond."""
    url = (base_url or get_core_service_url()) + "/api/approval/respond"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={
                "proposal_id": proposal_id,
                "decision": decision,
                "note": note,
            }, headers=get_auth_headers())
            # A 400 carries {"ok": false, "message": "...already EXPIRED"}; keep that message.
            try:
                data = resp.json()
                if isinstance(data, dict):
                    data.setdefault("ok", resp.status_code == 200)
                    return data
            except ValueError:
                pass
            return {"ok": resp.status_code == 200, "message": resp.text}
    except Exception as e:
        return {"ok": False, "message": str(e)}


async def cancel_chat_request(
    request_id: str,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Posts request cancellation to /api/chat/cancel."""
    url = (base_url or get_core_service_url()) + "/api/chat/cancel"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, json={"request_id": request_id}, headers=get_auth_headers())
            return resp.json() if resp.status_code == 200 else {"ok": False, "message": resp.text}
    except Exception as e:
        return {"ok": False, "message": str(e)}
