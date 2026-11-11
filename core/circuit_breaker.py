"""
core/circuit_breaker.py
Hardened deterministic keyed circuit breaker for Project-Z (Z.A.I.N.E).
Implements Claude Sonnet 5.5 backend criteria:
- Keyed per (tool, target)
- 4 States: CLOSED, RECORDING, OPEN, HALF_OPEN
- Purely deterministic; NO LLM calls on error path
- Exponential backoff cooldown (30s -> 60s -> 120s ... cap 300s)
- Closes the R1 race condition by expiring orphaned approvals when tripping OPEN
- Asynchronous idle reflection candidate rule formulation hook
"""

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from db.learned_rules import record_failure_event, upsert_candidate_rule

logger = logging.getLogger("zaine.core.circuit_breaker")


class CircuitState(str, enum.Enum):
    CLOSED = "CLOSED"
    RECORDING = "RECORDING"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class BreakerEntry:
    key: str
    tool: str
    target: Optional[str]
    state: CircuitState = CircuitState.CLOSED
    failure_timestamps: List[float] = field(default_factory=list)
    opened_at: Optional[float] = None
    cooldown_s: float = 30.0
    probe_in_flight: bool = False
    consecutive_opens: int = 0


class CircuitBreakerManager:
    _instance: Optional["CircuitBreakerManager"] = None
    _lock = threading.Lock()

    def __init__(
        self,
        failure_threshold: int = 3,
        window_seconds: float = 60.0,
        base_cooldown_seconds: float = 30.0,
        max_cooldown_seconds: float = 300.0
    ):
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.base_cooldown_seconds = base_cooldown_seconds
        self.max_cooldown_seconds = max_cooldown_seconds
        self._breakers: Dict[str, BreakerEntry] = {}
        self._mutex = threading.Lock()

    @classmethod
    def get_instance(cls) -> "CircuitBreakerManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _make_key(self, tool: str, target: Optional[str] = None) -> str:
        clean_tool = (tool or "unknown_tool").strip().lower()
        clean_target = (target or "").strip().lower()
        return f"{clean_tool}:{clean_target}" if clean_target else clean_tool

    def can_execute(self, tool: str, target: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Determines if an execution can proceed.
        Returns: (allowed: bool, reason_or_error: Optional[str])
        """
        key = self._make_key(tool, target)
        now = time.time()

        with self._mutex:
            breaker = self._breakers.get(key)
            if not breaker:
                return True, None

            if breaker.state == CircuitState.CLOSED:
                return True, None

            if breaker.state == CircuitState.OPEN:
                elapsed = now - (breaker.opened_at or 0.0)
                if elapsed >= breaker.cooldown_s:
                    # Transition to HALF_OPEN for a single probe call
                    breaker.state = CircuitState.HALF_OPEN
                    breaker.probe_in_flight = True
                    logger.info("Circuit breaker for [%s] transitioned to HALF_OPEN (probe allowed)", key)
                    return True, None
                else:
                    remaining = int(breaker.cooldown_s - elapsed)
                    reason = f"[UNAVAILABLE: tool '{tool}' circuit is OPEN after repeated failures. Cooldown: {remaining}s]"
                    return False, reason

            if breaker.state == CircuitState.HALF_OPEN:
                if not breaker.probe_in_flight:
                    # Allow one probe
                    breaker.probe_in_flight = True
                    return True, None
                else:
                    # Another probe is already running; block
                    reason = f"[UNAVAILABLE: tool '{tool}' is in HALF_OPEN testing probe]"
                    return False, reason

            return True, None

    def record_success(self, tool: str, target: Optional[str] = None) -> None:
        """Records a successful tool execution, resetting failure counters."""
        key = self._make_key(tool, target)
        with self._mutex:
            breaker = self._breakers.get(key)
            if not breaker:
                return

            if breaker.state == CircuitState.HALF_OPEN:
                logger.info("Probe succeeded for [%s]! Circuit reset to CLOSED.", key)
                breaker.state = CircuitState.CLOSED
                breaker.failure_timestamps.clear()
                breaker.cooldown_s = self.base_cooldown_seconds
                breaker.consecutive_opens = 0
                breaker.probe_in_flight = False
                try:
                    from satellite_hud.state_reducer import hud_state_reducer
                    hud_state_reducer.dispatch("BREAKER_TRANSITION", {"state": "CLOSED", "key": key})
                except Exception:
                    pass
            elif breaker.state == CircuitState.CLOSED:
                # Prune old timestamps
                now = time.time()
                breaker.failure_timestamps = [
                    t for t in breaker.failure_timestamps
                    if now - t <= self.window_seconds
                ]

    def record_failure(
        self,
        tool: str,
        error_class: str,
        message: str,
        target: Optional[str] = None,
        request_id: Optional[str] = None,
        agent_id: str = "zaine-core",
        duration_ms: Optional[int] = None
    ) -> Tuple[CircuitState, str]:
        """
        Records a caught failure deterministically.
        Zero LLM calls. Writes to failure_events black box.
        Transitions to OPEN if failure threshold is breached.
        """
        key = self._make_key(tool, target)
        now = time.time()

        with self._mutex:
            breaker = self._breakers.get(key)
            if not breaker:
                breaker = BreakerEntry(
                    key=key,
                    tool=tool,
                    target=target,
                    cooldown_s=self.base_cooldown_seconds
                )
                self._breakers[key] = breaker

            state_before = breaker.state

            # Prune sliding window
            breaker.failure_timestamps = [
                t for t in breaker.failure_timestamps
                if now - t <= self.window_seconds
            ]
            breaker.failure_timestamps.append(now)

            if breaker.state == CircuitState.HALF_OPEN:
                # Probe failed! Immediately snap back to OPEN with doubled cooldown
                breaker.consecutive_opens += 1
                breaker.cooldown_s = min(
                    breaker.cooldown_s * 2.0,
                    self.max_cooldown_seconds
                )
                breaker.opened_at = now
                breaker.state = CircuitState.OPEN
                breaker.probe_in_flight = False
                logger.warning(
                    "Circuit probe failed for [%s]! Back to OPEN. New cooldown: %.1fs",
                    key, breaker.cooldown_s
                )
                self._handle_trip_open(key, request_id)

            elif breaker.state == CircuitState.CLOSED:
                if len(breaker.failure_timestamps) >= self.failure_threshold:
                    breaker.state = CircuitState.OPEN
                    breaker.opened_at = now
                    breaker.consecutive_opens += 1
                    logger.warning(
                        "Circuit breaker tripped OPEN for [%s]! %d failures in %.1fs. Cooldown: %.1fs",
                        key, len(breaker.failure_timestamps), self.window_seconds, breaker.cooldown_s
                    )
                    self._handle_trip_open(key, request_id)

            state_after = breaker.state

        # Log synchronously to failure_events blackbox table (Zero LLM call)
        ok, fp = record_failure_event(
            error_class=error_class,
            message=message,
            tool=tool,
            agent_id=agent_id,
            request_id=request_id,
            retryable=False,
            breaker_before=state_before.value,
            breaker_after=state_after.value,
            duration_ms=duration_ms
        )

        return state_after, fp

    def _handle_trip_open(self, key: str, request_id: Optional[str] = None) -> None:
        """
        Actions executed when a breaker transitions to OPEN:
        1. Expire orphaned approval proposals tied to request_id (fixes Claude bug R1).
        2. Propose candidate rule deterministically.
        """
        if request_id:
            try:
                import approval
                if hasattr(approval, "expire_proposals_for_request"):
                    approval.expire_proposals_for_request(request_id)
                    logger.info("Expired orphaned approvals for request %s on circuit trip", request_id)
            except Exception as e:
                logger.debug("Approval expiry hook notice: %s", e)

        # Upsert deterministic candidate rule
        tool_name = key.split(":")[0]
        rule_text = f"Tool '{tool_name}' failed repeatedly. Check parameters or network connectivity before retrying."
        upsert_candidate_rule(
            rule_text=rule_text,
            scope="tool",
            trigger_tool=tool_name,
            trigger_error_class="RepeatedFailure",
            source="deterministic",
            trust="DERIVED",
            auto_activate=False
        )

        try:
            from satellite_hud.state_reducer import hud_state_reducer
            hud_state_reducer.dispatch("BREAKER_TRANSITION", {"state": "OPEN", "key": key})
        except Exception:
            pass

    def get_breaker_status(self, tool: str, target: Optional[str] = None) -> Dict[str, Any]:
        """Returns the current state dictionary for a given breaker key."""
        key = self._make_key(tool, target)
        with self._mutex:
            breaker = self._breakers.get(key)
            if not breaker:
                return {"key": key, "state": CircuitState.CLOSED.value, "failures": 0}
            return {
                "key": key,
                "state": breaker.state.value,
                "failures": len(breaker.failure_timestamps),
                "cooldown_s": breaker.cooldown_s,
                "opened_at": breaker.opened_at,
                "consecutive_opens": breaker.consecutive_opens
            }

    def reset(self) -> None:
        """Resets all breakers to CLOSED (for testing and manual overrides)."""
        with self._mutex:
            self._breakers.clear()


def get_circuit_breaker() -> CircuitBreakerManager:
    return CircuitBreakerManager.get_instance()
