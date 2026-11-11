"""
autonomy/cancel.py
Thread-safe HTTP/Ollama socket cancellation and active autonomous-run registry.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple


def _close_response_socket(resp: Any) -> None:
    """Best-effort immediate socket shutdown/close to abort blocked streaming reads."""
    if resp is None:
        return
    try:
        raw = getattr(resp, "raw", None)
        fp = getattr(raw, "_fp", None) if raw is not None else None
        raw_fp = getattr(fp, "fp", None) if fp is not None else None
        sock = getattr(raw_fp, "raw", None)
        sock = getattr(sock, "_sock", sock) if sock is not None else None
        if sock is None and raw is not None:
            sock = getattr(raw, "_sock", None)
        if sock is not None and hasattr(sock, "close"):
            try:
                if hasattr(sock, "shutdown"):
                    sock.shutdown(2)
            except Exception:
                pass
            sock.close()
    except Exception:
        pass
    try:
        if hasattr(resp, "close"):
            resp.close()
    except Exception:
        pass


class CancelToken:
    """Thread-safe cancellation token capable of aborting active HTTP/Ollama streams."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._closeables: List[Any] = []

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self._event.wait(timeout=timeout)

    def register_response(self, resp: Any) -> None:
        with self._lock:
            if self._event.is_set():
                _close_response_socket(resp)
                return
            self._closeables.append(resp)

    def unregister_response(self, resp: Any) -> None:
        with self._lock:
            self._closeables = [r for r in self._closeables if r is not resp]

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            targets = list(self._closeables)
            self._closeables.clear()
        for resp in targets:
            _close_response_socket(resp)


_ACTIVE_RUNS_LOCK = threading.Lock()
_ACTIVE_RUNS: Dict[str, Tuple[Optional[str], CancelToken]] = {}


def register_active_run(run_id: str, request_id: Optional[str], token: CancelToken) -> None:
    """Registers an active run so /api/chat/cancel or /stop can abort it immediately."""
    with _ACTIVE_RUNS_LOCK:
        _ACTIVE_RUNS[run_id] = (request_id, token)


def unregister_active_run(run_id: str) -> None:
    """Removes a completed or stopped run from the active cancellation registry."""
    with _ACTIVE_RUNS_LOCK:
        _ACTIVE_RUNS.pop(run_id, None)


def cancel_run(target_id: Optional[str] = None) -> int:
    """Cancels matching active run(s) by run_id or request_id (or all if empty). Returns count."""
    targets: List[CancelToken] = []
    clean = (target_id or "").strip()
    with _ACTIVE_RUNS_LOCK:
        for run_id, (req_id, tok) in _ACTIVE_RUNS.items():
            if not clean or clean == run_id or (req_id and clean == req_id):
                targets.append(tok)
    for tok in targets:
        tok.cancel()
    return len(targets)


def get_active_runs() -> List[Dict[str, Optional[str]]]:
    """Returns snapshots of currently active autonomous runs."""
    with _ACTIVE_RUNS_LOCK:
        return [
            {"run_id": rid, "request_id": req_id, "cancelled": tok.cancelled}
            for rid, (req_id, tok) in _ACTIVE_RUNS.items()
        ]

