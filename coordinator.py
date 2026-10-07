"""
coordinator.py — Centralized Request Coordinator & Atomic Idempotency Engine for Z.A.I.N.E

Provides:
1. Explicit request state tracking: "queued", "running", "completed", "failed".
2. Instant status visibility: waiting requests receive immediate queued feedback
   instead of invisibly blocking on an opaque lock.
3. Atomic check-and-claim idempotency: concurrent requests with identical request_ids
   atomically reuse the in-flight execution without duplicate tool or LLM runs.
4. Future-proof schema: includes client, session_id, and agent_id hooks for Phase 2b multi-agent.
"""

import time
import threading
from typing import Dict, List, Optional, Tuple, Any


class ManagedRequest:
    """Represents a single conversational or tool execution request in the core coordinator."""

    def __init__(
        self,
        request_id: str,
        client: str = "unknown",
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None
    ):
        self.request_id = request_id
        self.client = client
        self.session_id = session_id
        self.agent_id = agent_id

        self.state: str = "queued"  # "queued", "running", "completed", "failed"
        self.position: int = 0
        self.queued_at: float = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None

        # Signaled when this request's execution finishes (completed or failed)
        self.event = threading.Event()
        # Signaled when it is this request's turn to begin execution
        self.turn_event = threading.Event()

        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.waiters: int = 0
        self.thread_id: Optional[int] = None

    def wait_for_turn(self, timeout: float = 120.0) -> bool:
        """Blocks until the coordinator grants this request the turn to execute."""
        return self.turn_event.wait(timeout=timeout)

    def wait_for_completion(self, timeout: float = 120.0) -> bool:
        """Blocks until the in-flight request finishes (either completed or failed). Returns False if genuinely timed out."""
        return self.event.wait(timeout=timeout)

    def wait_for_result(self, timeout: float = 120.0) -> Optional[dict]:
        """
        Blocks until an in-flight duplicate request completes.
        Returns the successful result dict, or an error dict if failed.
        Returns None only if the wait genuinely timed out without the event being set.
        """
        finished = self.event.wait(timeout=timeout)
        if not finished:
            return None
        if self.state == "failed":
            return {"ok": False, "state": "failed", "error": self.error or "Request failed"}
        return self.result

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "client": self.client,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "state": self.state,
            "position": self.position,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "waiters": self.waiters,
        }


class RequestCoordinator:
    """
    Centralized coordinator managing request serialization, queue visibility,
    and atomic idempotency for Z.A.I.N.E Core Service.
    """

    IDEMPOTENCY_TTL_SECONDS = 300.0
    IDEMPOTENCY_MAX_ENTRIES = 100

    def __init__(self):
        self._lock = threading.RLock()
        self._completed_responses: Dict[str, Tuple[float, dict]] = {}
        self._in_flight_registry: Dict[str, ManagedRequest] = {}
        self._request_queue: List[ManagedRequest] = []
        self._current_running_request: Optional[ManagedRequest] = None

    def claim_request(
        self,
        request_id: str,
        client: str = "unknown",
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None
    ) -> Tuple[str, Optional[ManagedRequest], Optional[dict]]:
        """
        Atomically checks completed cache and in-flight registry, claiming the request under a single lock.

        Returns:
            ("completed", None, cached_dict) -> Already finished, return cached result immediately.
            ("in_flight", req, None)        -> Duplicate request_id currently processing, caller should wait.
            ("claimed", req, None)          -> Newly claimed request. Check req.state ("running" or "queued").
        """
        if not request_id:
            raise ValueError("request_id cannot be empty")

        with self._lock:
            now = time.time()

            # 1. Check completed response cache
            entry = self._completed_responses.get(request_id)
            if entry:
                ts, resp = entry
                if now - ts < self.IDEMPOTENCY_TTL_SECONDS:
                    return ("completed", None, resp)
                else:
                    self._completed_responses.pop(request_id, None)

            # 2. Check in-flight registry (distinct from completed cache)
            if request_id in self._in_flight_registry:
                in_flight_req = self._in_flight_registry[request_id]
                in_flight_req.waiters += 1
                return ("in_flight", in_flight_req, None)

            # 3. Atomically claim execution as a new in-flight request
            req = ManagedRequest(
                request_id=request_id,
                client=client,
                session_id=session_id,
                agent_id=agent_id
            )
            self._in_flight_registry[request_id] = req

            if self._current_running_request is None:
                # Core is idle -> immediately grant execution turn
                self._current_running_request = req
                req.state = "running"
                req.started_at = now
                req.position = 0
                req.turn_event.set()
            else:
                # Core is currently busy -> place in FIFO queue
                req.state = "queued"
                self._request_queue.append(req)
                req.position = len(self._request_queue)

            return ("claimed", req, None)

    def complete_request(self, request_id: str, result: dict):
        """Marks a claimed request as successfully completed, saves result to cache, and unblocks waiters."""
        with self._lock:
            now = time.time()
            req = self._in_flight_registry.pop(request_id, None)

            # Store in completed response cache
            self._cache_completed_locked(request_id, result, now)

            if req:
                req.state = "completed"
                req.completed_at = now
                req.result = result
                req.event.set()

            # If this was the active running request, release and advance
            if self._current_running_request and self._current_running_request.request_id == request_id:
                self._current_running_request = None

            self._advance_queue_locked()

    def fail_request(self, request_id: str, error: str):
        """Marks a claimed request as failed, stores error payload, notifies waiters, and advances the queue."""
        with self._lock:
            now = time.time()
            req = self._in_flight_registry.pop(request_id, None)
            if req:
                req.state = "failed"
                req.completed_at = now
                req.error = error
                req.result = {"ok": False, "state": "failed", "error": error}
                req.event.set()

            if self._current_running_request and self._current_running_request.request_id == request_id:
                self._current_running_request = None

            self._advance_queue_locked()

    def cancel_request(self, request_id: str):
        """Cancels a queued or in-flight request, unblocking waiters and advancing queue."""
        with self._lock:
            req = self._in_flight_registry.pop(request_id, None)
            if req:
                if req in self._request_queue:
                    self._request_queue.remove(req)
                req.state = "failed"
                req.error = "Request cancelled"
                req.result = {"ok": False, "state": "failed", "error": "Request cancelled"}
                req.turn_event.set()
                req.event.set()

            if self._current_running_request and self._current_running_request.request_id == request_id:
                self._current_running_request = None

            self._advance_queue_locked()

    def _advance_queue_locked(self):
        """Grants execution turn to the next request waiting in the FIFO queue."""
        if self._current_running_request is not None:
            return

        while self._request_queue:
            next_req = self._request_queue.pop(0)
            if next_req.request_id in self._in_flight_registry:
                self._current_running_request = next_req
                next_req.state = "running"
                next_req.started_at = time.time()
                next_req.turn_event.set()

                # Recalculate remaining positions
                for idx, r in enumerate(self._request_queue):
                    r.position = idx + 1
                break

    def _cache_completed_locked(self, request_id: str, result: dict, timestamp: float):
        """Stores result in completed cache with bounded LRU eviction."""
        if len(self._completed_responses) >= self.IDEMPOTENCY_MAX_ENTRIES:
            stale = [k for k, (ts, _) in self._completed_responses.items() if timestamp - ts > self.IDEMPOTENCY_TTL_SECONDS]
            for k in stale:
                self._completed_responses.pop(k, None)
            if len(self._completed_responses) >= self.IDEMPOTENCY_MAX_ENTRIES:
                oldest_key = min(self._completed_responses.keys(), key=lambda k: self._completed_responses[k][0])
                self._completed_responses.pop(oldest_key, None)
        self._completed_responses[request_id] = (timestamp, result)

    def get_request_status(self, request_id: str) -> dict:
        """Returns the real-time coordinator state for a specific request_id."""
        with self._lock:
            if request_id in self._in_flight_registry:
                req = self._in_flight_registry[request_id]
                return {
                    "ok": True,
                    "request_id": request_id,
                    "state": req.state,
                    "position": req.position if req.state == "queued" else 0,
                    "client": req.client,
                    "queued_at": req.queued_at,
                    "started_at": req.started_at,
                    "waiters": req.waiters,
                }
            if request_id in self._completed_responses:
                return {
                    "ok": True,
                    "request_id": request_id,
                    "state": "completed",
                    "position": 0,
                }
            return {
                "ok": False,
                "request_id": request_id,
                "state": "unknown",
            }

    def get_queue_telemetry(self) -> dict:
        """Returns a snapshot of active, queued, and cached requests."""
        with self._lock:
            return {
                "ok": True,
                "running": self._current_running_request.request_id if self._current_running_request else None,
                "running_client": self._current_running_request.client if self._current_running_request else None,
                "queue_depth": len(self._request_queue),
                "queued_requests": [
                    {
                        "request_id": r.request_id,
                        "client": r.client,
                        "position": r.position,
                        "queued_at": r.queued_at,
                    }
                    for r in self._request_queue
                ],
                "in_flight_count": len(self._in_flight_registry),
                "completed_cache_count": len(self._completed_responses),
            }

    def reset_for_testing(self):
        """Resets all internal coordinator states for test isolation."""
        with self._lock:
            self._completed_responses.clear()
            self._in_flight_registry.clear()
            self._request_queue.clear()
            self._current_running_request = None


# Singleton instance shared across ui.py and core agent components
_GLOBAL_COORDINATOR = RequestCoordinator()


def get_request_coordinator() -> RequestCoordinator:
    """Returns the global RequestCoordinator instance."""
    return _GLOBAL_COORDINATOR
