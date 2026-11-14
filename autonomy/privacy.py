"""
autonomy/privacy.py
Local-first privacy taint tracking and cloud-routing boundary enforcement.

Invariants (Constraint #4):
- Memory items carry a privacy taint, LOCAL_ONLY by default.
- Once LOCAL_ONLY data enters the session (or TaskEnvelope.privacy_class == 'LOCAL_ONLY'),
  any attempt to route inference or private payloads to cloud endpoints is blocked.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterator, List, Optional, Tuple
from urllib.parse import urlparse

LOCAL_HOSTS: FrozenSet[str] = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0", "[::1]"})

CLOUD_LLM_HOST_FRAGMENTS: Tuple[str, ...] = (
    "api.openai.com",
    "openai.com",
    "api.anthropic.com",
    "anthropic.com",
    "generativelanguage.googleapis.com",
    "aiplatform.googleapis.com",
    "api.groq.com",
    "openrouter.ai",
    "api.together.xyz",
    "api.cohere.ai",
    "api.mistral.ai",
    "api.perplexity.ai",
    "huggingface.co/api",
    "api.replicate.com",
    "openai.azure.com",
    "bedrock-runtime",
    "integrate.api.nvidia.com",
    "api.nvidia.com",
)


class PrivacyViolationError(RuntimeError):
    """Raised when cloud routing is attempted while private LOCAL_ONLY data is in session."""


@dataclass
class SessionPrivacyState:
    """Tracks whether LOCAL_ONLY private data has entered the current execution session."""

    taint: str = "CLEAN"
    sources: List[str] = field(default_factory=list)

    def mark(self, source: str, privacy_taint: str = "LOCAL_ONLY") -> None:
        norm = str(privacy_taint or "LOCAL_ONLY").strip().upper()
        if norm == "LOCAL_ONLY":
            self.taint = "LOCAL_ONLY"
            src = str(source or "memory").strip()[:120]
            if src and src not in self.sources and len(self.sources) < 50:
                self.sources.append(src)


_PRIVACY_STATE_VAR: ContextVar[Optional[SessionPrivacyState]] = ContextVar(
    "zaine_session_privacy_state", default=None
)


@contextmanager
def scoped_privacy_session(initial_taint: str = "CLEAN") -> Iterator[SessionPrivacyState]:
    """Creates an isolated privacy taint scope for a single run or test."""
    norm = "LOCAL_ONLY" if str(initial_taint or "").strip().upper() == "LOCAL_ONLY" else "CLEAN"
    state = SessionPrivacyState(taint=norm)
    tok = _PRIVACY_STATE_VAR.set(state)
    try:
        yield state
    finally:
        _PRIVACY_STATE_VAR.reset(tok)


def reset_privacy_session() -> None:
    """Clears thread/context privacy state cleanly."""
    _PRIVACY_STATE_VAR.set(None)


def get_privacy_state() -> Optional[SessionPrivacyState]:
    return _PRIVACY_STATE_VAR.get(None)


def mark_session_private(source: str, privacy_taint: str = "LOCAL_ONLY") -> SessionPrivacyState:
    """Records entry of memory/private data into the current session."""
    state = _PRIVACY_STATE_VAR.get(None)
    if state is None:
        state = SessionPrivacyState()
        _PRIVACY_STATE_VAR.set(state)
    state.mark(source, privacy_taint=privacy_taint)
    return state


def is_session_private() -> bool:
    """Returns True if the active session holds LOCAL_ONLY taint or a LOCAL_ONLY TaskEnvelope."""
    state = _PRIVACY_STATE_VAR.get(None)
    if state is not None and state.taint == "LOCAL_ONLY":
        return True
    try:
        from core.task_envelope import current_envelope_var

        env = current_envelope_var.get(None)
        if env is not None and str(getattr(env, "privacy_class", "LOCAL_ONLY")).strip().upper() == "LOCAL_ONLY":
            return True
    except Exception:
        pass
    return False


def is_cloud_endpoint(url_or_target: str, *, strict_llm_route: bool = True) -> bool:
    """
    Returns True if `url_or_target` resolves to a cloud / non-local endpoint.
    Loopback hosts (127.0.0.1, localhost, ::1) remain local.
    """
    raw = str(url_or_target or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if any(frag in low for frag in CLOUD_LLM_HOST_FRAGMENTS):
        return True

    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host in LOCAL_HOSTS:
        return False
    return bool(strict_llm_route)


def assert_local_routing(url_or_target: str, *, context: str = "model_call") -> None:
    """
    Blocks non-local model/cloud routing when private LOCAL_ONLY data is in session.
    Raises PrivacyViolationError on violation.
    """
    if not is_session_private():
        return
    if is_cloud_endpoint(url_or_target, strict_llm_route=True):
        state = get_privacy_state()
        srcs = ", ".join(state.sources[:3]) if state and state.sources else "LOCAL_ONLY session"
        raise PrivacyViolationError(
            f"Cloud routing blocked during {context}: session holds LOCAL_ONLY data ({srcs}); "
            f"remote endpoint '{url_or_target}' is not permitted."
        )


def check_outbound_cloud_block(tool_name: str, args: Dict[str, Any]) -> Optional[str]:
    """
    Pre-approval guard checking if a side-effecting tool attempts to route to a
    cloud LLM/provider while LOCAL_ONLY private data is in the active session.
    """
    if not is_session_private():
        return None
    tname = (tool_name or "").strip()
    candidates: List[str] = []
    for key in ("url", "endpoint_url", "endpoint", "base_url", "api_url", "command"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())

    for cand in candidates:
        low = cand.lower()
        if any(frag in low for frag in CLOUD_LLM_HOST_FRAGMENTS):
            return (
                f"Privacy boundary blocked: tool '{tname}' references cloud endpoint '{cand[:120]}' "
                "while session carries LOCAL_ONLY private data."
            )
    if tname == "query_public_api" and candidates:
        if is_cloud_endpoint(candidates[0], strict_llm_route=True):
            # Allow explicitly localhost APIs; block non-local AI APIs cleanly
            if any(frag in candidates[0].lower() for frag in CLOUD_LLM_HOST_FRAGMENTS):
                return (
                    f"Privacy boundary blocked: tool '{tname}' cannot call cloud AI endpoint "
                    f"while session holds LOCAL_ONLY data."
                )
    return None
