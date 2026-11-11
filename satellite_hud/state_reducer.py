"""
satellite_hud/state_reducer.py
Single-Reducer State Machine & Real-Time SSE Event Bus for the Living Arc Reactor HUD.

Aggregates hardware telemetry, circuit breaker trips, inference velocity (tok/s),
and subagent transitions into an atomic state vector broadcast to WebView2 / browser clients.
"""

import json
import queue
import threading
import time
from typing import Any, Dict, List, Optional


class HudStateReducer:
    def __init__(self):
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {
            "vram_used_mb": 0.0,
            "vram_total_mb": 4096.0,
            "tokens_per_sec": 0.0,
            "active_subagent": "jarvis",
            "breaker_state": "CLOSED",
            "voice_state": "IDLE",
            "system_status": "HEALTHY",
            "last_event": "SYSTEM_INIT",
            "timestamp": time.time(),
        }
        self._subscribers: List[queue.Queue] = []

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def dispatch(self, action_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Dispatches an atomic state mutation and notifies all SSE listener queues.
        """
        payload = payload or {}
        with self._lock:
            old_state = dict(self._state)
            if action_type == "TELEMETRY_UPDATE":
                if "vram_used_mb" in payload:
                    self._state["vram_used_mb"] = float(payload["vram_used_mb"])
                if "tokens_per_sec" in payload:
                    self._state["tokens_per_sec"] = float(payload["tokens_per_sec"])
            elif action_type == "AGENT_SWITCH":
                self._state["active_subagent"] = str(payload.get("agent_id", "jarvis")).lower()
            elif action_type == "BREAKER_TRANSITION":
                self._state["breaker_state"] = str(payload.get("state", "CLOSED")).upper()
                if self._state["breaker_state"] == "OPEN":
                    self._state["system_status"] = "REFLECTING"
                elif self._state["breaker_state"] == "CLOSED":
                    self._state["system_status"] = "HEALTHY"
            elif action_type == "VOICE_STATE_CHANGE":
                self._state["voice_state"] = str(payload.get("state", "IDLE")).upper()
            elif action_type == "SYSTEM_STATUS":
                self._state["system_status"] = str(payload.get("status", "HEALTHY")).upper()

            self._state["last_event"] = action_type
            self._state["timestamp"] = time.time()
            new_state = dict(self._state)

            # Broadcast to active SSE listeners
            dead_subscribers = []
            msg = f"data: {json.dumps(new_state)}\n\n"
            for q in self._subscribers:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    dead_subscribers.append(q)

            for d in dead_subscribers:
                if d in self._subscribers:
                    self._subscribers.remove(d)

        return new_state

    def register_subscriber(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=32)
        with self._lock:
            # Deliver current snapshot immediately upon connection
            q.put_nowait(f"data: {json.dumps(self._state)}\n\n")
            self._subscribers.append(q)
        return q

    def unregister_subscriber(self, q: queue.Queue):
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)


# Global singleton
hud_state_reducer = HudStateReducer()

