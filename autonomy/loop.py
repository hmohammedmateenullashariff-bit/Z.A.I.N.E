"""
autonomy/loop.py
Plan -> Act -> Observe -> Reflect autonomous execution loop for Project-Z (Z.A.I.N.E).

Reuses:
- core.circuit_breaker.CircuitBreakerManager (keyed circuit breaker & failure blackbox)
- core.task_envelope (TaskEnvelope, ResultEnvelope, is_tool_permitted, ContextVars)
- harness (CallTracker, ResultStore, tool_outcome, compact, result_char_limit)

All behavior sits behind ZAINE_AGENT=1 (default OFF). Runs strictly on the single
resident local model via Ollama with num_ctx<=4096 unless explicitly overridden.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple

import requests

from autonomy.cancel import (
    CancelToken,
    _close_response_socket,
    cancel_run,
    get_active_runs,
    register_active_run,
    unregister_active_run,
)
from autonomy.guards import preapproved_tool_scope, require_side_effect_approval
from autonomy.memory_bridge import retrieve_step_memory
from autonomy.privacy import (
    PrivacyViolationError,
    assert_local_routing,
    get_privacy_state,
    mark_session_private,
    scoped_privacy_session,
)
from autonomy.sandbox import resolve_sandbox_path
from autonomy.scratchpad import (
    RunScratchpad,
    RunScratchpadStore,
    build_resume_context,
    flush_run_to_vault,
)
from autonomy.tool_validation import (
    ToolValidationResult,
    looks_like_tool_attempt,
    validate_and_repair_tool_calls,
)
from autonomy.untrusted import (
    UNTRUSTED_SOURCE_TOOLS,
    contains_injection_attempt,
    extract_injected_tool_names,
    wrap_untrusted_content,
)
from core.circuit_breaker import CircuitBreakerManager, get_circuit_breaker
from core.task_envelope import (
    TaskEnvelope,
    current_agent_var,
    current_envelope_var,
    is_tool_permitted,
)
from harness import CallTracker, ResultStore, ToolOutcome, compact, result_char_limit, tool_outcome

OLLAMA_URL = "http://localhost:11434/api/chat"


@dataclass
class LoopConfig:
    """Runtime budgets and local-model parameters for AutonomousLoop."""

    max_steps: int = 8
    wall_clock_timeout_s: float = 180.0
    no_progress_limit: int = 3
    identical_failure_limit: int = 3
    num_ctx: int = 4096
    model_name: str = "zaine-reflex-7b"
    request_timeout_s: float = 120.0
    plan_max_tokens: int = 220
    act_max_tokens: int = 768
    temperature: float = 0.3
    max_memory_chars: int = 2000

    @classmethod
    def from_env(cls, **overrides: Any) -> "LoopConfig":
        raw_ctx = int(os.getenv("ZAINE_AGENT_NUM_CTX", os.getenv("ZAINE_NUM_CTX", "4096")) or 4096)
        # Keep within tested 4096 VRAM ceiling unless explicitly overridden in code/tests
        capped_ctx = min(raw_ctx, 4096) if "num_ctx" not in overrides else overrides["num_ctx"]
        base = cls(
            max_steps=max(1, int(os.getenv("ZAINE_AGENT_MAX_STEPS", "8") or 8)),
            wall_clock_timeout_s=max(1.0, float(os.getenv("ZAINE_AGENT_TIMEOUT_S", "180.0") or 180.0)),
            no_progress_limit=max(1, int(os.getenv("ZAINE_AGENT_NO_PROGRESS_LIMIT", "3") or 3)),
            identical_failure_limit=max(1, int(os.getenv("ZAINE_AGENT_FAIL_LIMIT", "3") or 3)),
            num_ctx=capped_ctx,
            model_name=os.getenv("ZAINE_AGENT_MODEL", "zaine-reflex-7b"),
            request_timeout_s=max(5.0, float(os.getenv("ZAINE_AGENT_REQ_TIMEOUT_S", "120.0") or 120.0)),
        )
        for k, v in overrides.items():
            if hasattr(base, k) and v is not None:
                setattr(base, k, v)
        return base


@dataclass
class StepRecord:
    """Structured telemetry record for a single Plan/Act/Observe/Reflect iteration."""

    step: int
    max_steps: int
    phase: str
    tool: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    outcome_status: str = ""
    error_kind: str = ""
    progress_made: bool = False
    reflection: str = ""
    result_preview: str = ""
    duration_s: float = 0.0


@dataclass
class LoopResult:
    """Terminal result returned by AutonomousLoop.run()."""

    run_id: str
    status: str  # completed | stopped_circuit_breaker | stopped_max_steps | stopped_timeout | cancelled | failed_validation | error
    summary: str
    plan: List[str] = field(default_factory=list)
    steps_executed: int = 0
    max_steps: int = 8
    artifacts: List[str] = field(default_factory=list)
    tool_history: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[StepRecord] = field(default_factory=list)
    stop_reason: str = ""
    elapsed_s: float = 0.0
    errors: List[str] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=lambda: {"model_calls": 0, "prompt_tokens": 0, "eval_tokens": 0})


EventCallback = Callable[[str, str, Any], None]
ModelStreamFn = Callable[[Dict[str, Any], CancelToken, float], Iterator[Dict[str, Any]]]
ToolExecFn = Callable[[Dict[str, Any]], str]
ToolAliasFn = Callable[[str], str]
CancelCheckFn = Callable[[], bool]


def _default_ollama_stream(payload: Dict[str, Any], cancel_token: CancelToken, timeout_s: float) -> Iterator[Dict[str, Any]]:
    """Streams /api/chat JSON chunks from Ollama while allowing instant socket cancellation."""
    if cancel_token.cancelled:
        return
    resp = None
    watch_stop = threading.Event()

    def _watch() -> None:
        while not watch_stop.wait(0.05):
            if cancel_token.cancelled:
                _close_response_socket(resp)
                break

    watcher: Optional[threading.Thread] = None
    target_url = os.getenv("ZAINE_OLLAMA_URL", "").strip() or OLLAMA_URL
    assert_local_routing(target_url, context="ollama_stream")
    try:
        resp = requests.post(target_url, json=payload, stream=True, timeout=(10.0, timeout_s))
        resp.raise_for_status()
        cancel_token.register_response(resp)
        watcher = threading.Thread(target=_watch, daemon=True, name="zaine-cancel-watch")
        watcher.start()
        for raw_line in resp.iter_lines():
            if cancel_token.cancelled:
                break
            if not raw_line:
                continue
            try:
                yield json.loads(raw_line)
            except Exception:
                continue
    finally:
        watch_stop.set()
        if watcher is not None:
            watcher.join(timeout=0.5)
        if resp is not None:
            cancel_token.unregister_response(resp)
            _close_response_socket(resp)


class AutonomousLoop:
    """
    Bounded autonomous execution loop implementing:
      Plan -> Act -> Observe -> Reflect
    over a single resident local Ollama model.
    """

    def __init__(
        self,
        *,
        config: Optional[LoopConfig] = None,
        profile: Optional[Any] = None,
        model_stream_fn: Optional[ModelStreamFn] = None,
        tool_exec_fn: Optional[ToolExecFn] = None,
        tool_alias_fn: Optional[ToolAliasFn] = None,
        breaker: Optional[CircuitBreakerManager] = None,
        system_prompt: str = "",
        tool_catalog_text: str = "",
        memory_context: str = "",
        request_id: Optional[str] = None,
        cancel_check: Optional[CancelCheckFn] = None,
        on_event: Optional[EventCallback] = None,
        cancel_token: Optional[CancelToken] = None,
        result_store: Optional[ResultStore] = None,
        allow_delegation: Optional[bool] = None,
        delegation_depth: int = 0,
        delegate_fn: Optional[Callable[[Dict[str, Any]], str]] = None,
        memory: Optional[Any] = None,
        scratchpad_store: Optional[RunScratchpadStore] = None,
        persist_scratchpad: Optional[bool] = None,
    ) -> None:
        self.config = config or LoopConfig.from_env()
        self.profile = profile
        self._model_stream_fn = model_stream_fn or _default_ollama_stream
        self._tool_exec_fn = tool_exec_fn or self._fallback_tool_exec
        self._tool_alias_fn = tool_alias_fn or (lambda name: name)
        self._breaker = breaker or get_circuit_breaker()
        self._base_system_prompt = system_prompt.strip()
        self._tool_catalog_text = tool_catalog_text.strip()
        self._memory_context = (memory_context or "").strip()[: self.config.max_memory_chars]
        self.request_id = request_id
        self._external_cancel_check = cancel_check
        self._on_event = on_event
        self.cancel_token = cancel_token or CancelToken()
        self._result_store = result_store if result_store is not None else ResultStore()
        self._delegation_depth = max(0, int(delegation_depth or 0))
        self._allow_delegation = (self._delegation_depth < 1) if allow_delegation is None else bool(allow_delegation)
        self._delegate_fn = delegate_fn
        self._memory = memory
        self._scratchpad_store = scratchpad_store
        self._persist_scratchpad = (self._delegation_depth == 0) if persist_scratchpad is None else bool(persist_scratchpad)
        self._last_model_calls: List[Dict[str, Any]] = []

    @staticmethod
    def _fallback_tool_exec(tc: Dict[str, Any]) -> str:
        from tools import TOOL_REGISTRY

        tname = tc.get("tool", "")
        args = dict(tc.get("args") or {})
        fn = TOOL_REGISTRY.get(tname)
        if fn is None:
            return f"Error: unknown tool '{tname}'"
        ignored: List[str] = []
        try:
            params = inspect.signature(fn).parameters
            if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
                ignored = [k for k in args if k not in params]
                args = {k: v for k, v in args.items() if k in params}
        except (TypeError, ValueError):
            pass
        out = str(fn(**args))
        if ignored:
            out += f"\n[note: ignored unsupported argument(s) for {tname}: {', '.join(ignored)}]"
        return out

    def _emit(self, stage: str, tool: str, data: Any) -> None:
        if not self._on_event:
            return
        try:
            self._on_event(stage, tool, data)
        except Exception:
            pass

    def _is_cancelled(self) -> bool:
        if self.cancel_token.cancelled:
            return True
        if self._external_cancel_check:
            try:
                if self._external_cancel_check():
                    self.cancel_token.cancel()
                    return True
            except Exception:
                pass
        return False

    def _check_budget(self, deadline: float, step: int) -> Optional[str]:
        if self._is_cancelled():
            return "cancelled"
        if time.monotonic() >= deadline:
            return "stopped_timeout"
        if step > self.config.max_steps:
            return "stopped_max_steps"
        return None

    def _resolved_model(self) -> str:
        try:
            from core_router import router
            if router.single_model:
                return router.resolve_model(self.config.model_name or "zaine-reflex-7b")
            return router.resolve_model(self.config.model_name or router.reflex_model)
        except Exception:
            return self.config.model_name or "zaine-reflex-7b"

    def _call_model(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int,
        deadline: float,
        step_label: str,
        emit_thinking: bool = True,
    ) -> Tuple[str, Dict[str, Any], Optional[str]]:
        """
        Invokes the resident local model with live SSE streaming telemetry and cancel support.
        Returns (assistant_text, metrics_dict, interrupt_status_or_None).
        """
        remaining = max(0.5, deadline - time.monotonic())
        if self._is_cancelled():
            return "", {}, "cancelled"
        if remaining <= 0.0:
            return "", {}, "stopped_timeout"

        active_model = self._resolved_model()
        single_model = os.getenv("ZAINE_SINGLE_MODEL", "1").strip().lower() in ("1", "true", "yes")
        payload = {
            "model": active_model,
            "messages": messages,
            "stream": True,
            "keep_alive": -1 if single_model else "5m",
            "options": {
                "num_ctx": int(self.config.num_ctx),
                "num_predict": int(max_tokens),
                "temperature": float(self.config.temperature),
                "num_thread": int(os.environ.get("ZAINE_NUM_THREAD", "6")),
                "top_p": 0.9,
                "repeat_penalty": 1.1,
            },
        }

        req_timeout = min(float(self.config.request_timeout_s), max(5.0, remaining))
        t0 = time.perf_counter()
        last_ping = time.monotonic()
        raw_parts: List[str] = []
        clean_parts: List[str] = []
        in_think = False
        metrics: Dict[str, Any] = {"model": active_model, "step": step_label}

        route_url = os.getenv("ZAINE_OLLAMA_URL", "").strip() or OLLAMA_URL
        assert_local_routing(route_url, context=f"loop.{step_label}")

        try:
            for chunk in self._model_stream_fn(payload, self.cancel_token, req_timeout):
                if self._is_cancelled():
                    return "".join(clean_parts), metrics, "cancelled"
                if time.monotonic() >= deadline:
                    return "".join(clean_parts), metrics, "stopped_timeout"

                if chunk.get("done"):
                    wall_s = round(time.perf_counter() - t0, 3)
                    metrics = {
                        "model": active_model,
                        "step": step_label,
                        "load_duration_s": round(chunk.get("load_duration", 0) / 1e9, 3),
                        "prompt_eval_count": int(chunk.get("prompt_eval_count") or 0),
                        "prompt_eval_duration_s": round(chunk.get("prompt_eval_duration", 0) / 1e9, 3),
                        "eval_count": int(chunk.get("eval_count") or 0),
                        "eval_duration_s": round(chunk.get("eval_duration", 0) / 1e9, 3),
                        "wall_time_s": wall_s,
                    }
                    self._last_model_calls.append(metrics)
                    self._emit("profiler", active_model, metrics)
                    try:
                        from ollama_profiler import log_ollama_call
                        log_ollama_call(
                            caller=f"autonomy.loop({step_label})",
                            model=active_model,
                            options=payload.get("options"),
                            response_data=chunk,
                            wall_time_s=wall_s,
                            keep_alive=payload["keep_alive"],
                        )
                    except Exception:
                        pass

                msg_obj = chunk.get("message") or {}
                think_tok = msg_obj.get("thinking", "")
                if think_tok and emit_thinking:
                    self._emit("think", "reasoning", think_tok)

                tok = msg_obj.get("content", "")
                if not tok:
                    continue
                raw_parts.append(tok)

                now_m = time.monotonic()
                if now_m - last_ping >= 3.0:
                    last_ping = now_m
                    self._emit("generating", active_model, {"step": step_label})

                # Intercept <think>...</think> spans across chunk boundaries without corrupting trailing JSON
                cursor = tok
                while cursor:
                    if in_think:
                        end_idx = cursor.find("</think>")
                        if end_idx == -1:
                            if emit_thinking and cursor:
                                self._emit("think", "reasoning", cursor)
                            cursor = ""
                        else:
                            head = cursor[:end_idx]
                            if emit_thinking and head:
                                self._emit("think", "reasoning", head)
                            in_think = False
                            if emit_thinking:
                                self._emit("think_done", "reasoning", "")
                            cursor = cursor[end_idx + len("</think>") :]
                    else:
                        start_idx = cursor.find("<think>")
                        if start_idx == -1:
                            clean_parts.append(cursor)
                            cursor = ""
                        else:
                            before = cursor[:start_idx]
                            if before:
                                clean_parts.append(before)
                            in_think = True
                            cursor = cursor[start_idx + len("<think>") :]
        except requests.Timeout:
            if time.monotonic() >= deadline:
                return "", metrics, "stopped_timeout"
            raise
        except Exception as exc:
            if self._is_cancelled():
                return "".join(clean_parts), metrics, "cancelled"
            if time.monotonic() >= deadline:
                return "".join(clean_parts), metrics, "stopped_timeout"
            raise RuntimeError(f"Model stream error during {step_label}: {exc}") from exc

        return "".join(clean_parts).strip(), metrics, None

    def plan(
        self,
        goal: str,
        *,
        run_id: str,
        deadline: float,
    ) -> Tuple[List[str], bool, Optional[str]]:
        """
        Phase 1: Plan — asks the resident 7B model for a compact JSON step plan.
        Returns (steps, direct_answer_hint, interrupt_status_or_None).
        """
        self._emit(
            "plan_start",
            "loop",
            {"run_id": run_id, "step": 0, "max_steps": self.config.max_steps, "goal": goal[:300]},
        )

        planner_sys = (
            "You are Z.A.I.N.E's task planner. Break the goal into 1 to 5 short concrete steps.\n"
            "Return ONLY compact JSON: {\"direct\": false, \"plan\": [\"step 1\", \"step 2\"]}.\n"
            "Set \"direct\": true only if the goal is pure conversation/question needing no tools."
        )
        if self._tool_catalog_text:
            planner_sys += f"\nAvailable tools summary:\n{self._tool_catalog_text[:900]}"
        if self._memory_context:
            planner_sys += f"\nContext:\n{self._memory_context[:600]}"

        text, _metrics, interrupted = self._call_model(
            [{"role": "system", "content": planner_sys}, {"role": "user", "content": goal}],
            max_tokens=self.config.plan_max_tokens,
            deadline=deadline,
            step_label="plan",
            emit_thinking=True,
        )
        if interrupted:
            return [], False, interrupted

        plan_steps, direct = self._parse_plan_output(text, goal)
        self._emit(
            "plan",
            "loop",
            {
                "run_id": run_id,
                "steps": plan_steps,
                "direct": direct,
                "max_steps": self.config.max_steps,
            },
        )
        return plan_steps, direct, None

    @staticmethod
    def _parse_plan_output(text: str, goal: str) -> Tuple[List[str], bool]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.IGNORECASE | re.MULTILINE)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                obj = json.loads(cleaned[start : end + 1])
                if isinstance(obj, dict):
                    raw_plan = obj.get("plan") or obj.get("steps") or []
                    if isinstance(raw_plan, list):
                        steps = [str(s).strip() for s in raw_plan if str(s).strip()][:6]
                        if steps:
                            return steps, bool(obj.get("direct", False))
            except Exception:
                pass
        lines = [re.sub(r"^\s*(?:\d+[.)]|[-*])\s*", "", ln).strip() for ln in cleaned.splitlines()]
        steps = [ln for ln in lines if ln and not ln.startswith("{")][:5]
        return (steps or [goal.strip()[:200]]), False

    def _build_act_system_prompt(self) -> str:
        parts = []
        if self._base_system_prompt:
            parts.append(self._base_system_prompt)
        else:
            parts.append(
                "You are Z.A.I.N.E executing an autonomous goal step-by-step.\n"
                "To call a tool, respond ONLY with valid double-quoted JSON:\n"
                '{"tool": "<tool_name>", "args": {"<param>": "<value>"}}\n'
                "When the goal is fully verified and complete, answer clearly in plain text without calling a tool."
            )
        if self._tool_catalog_text and self._tool_catalog_text not in self._base_system_prompt:
            parts.append(self._tool_catalog_text[:1400])
        if self._memory_context:
            parts.append(f"[MEMORY CONTEXT]\n{self._memory_context[:1200]}")
        parts.append(
            "STRICT OUTPUT RULE: When invoking a tool, output ONLY strict JSON "
            '{"tool": "...", "args": {...}} with double quotes and zero markdown commentary.'
        )
        return "\n\n".join(parts)

    def _check_tool_permission(self, raw_tool_name: str) -> Tuple[str, Optional[str]]:
        """Resolves alias and validates calling agent + TaskEnvelope permissions unconditionally."""
        resolved = self._tool_alias_fn(raw_tool_name)
        if resolved in ("delegate", "ask_agent") and (
            not self._allow_delegation or self._delegation_depth >= 1
        ):
            return resolved, (
                f"Permission denied: tool '{resolved}' is disabled inside subagents (delegation depth limit = 1)."
            )
        profile = self.profile
        if profile is not None and not profile.allows(resolved):
            return resolved, (
                f"Permission denied: tool '{resolved}' is outside "
                f"{getattr(profile, 'display_name', getattr(profile, 'agent_id', 'agent'))}'s allowed tools."
            )
        agent_id = getattr(profile, "agent_id", getattr(profile, "name", None)) if profile else None
        permitted, deny_reason = is_tool_permitted(resolved, agent_id)
        if not permitted:
            return resolved, deny_reason or f"Permission denied for tool '{resolved}'."
        return resolved, None

    @staticmethod
    def _extract_target_for_breaker(args: Dict[str, Any]) -> Optional[str]:
        for key in ("filepath", "path", "file_path", "url", "command", "package", "app_name"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:120]
        return None

    def _act_with_validation(
        self,
        messages: List[Dict[str, str]],
        *,
        step_idx: int,
        deadline: float,
    ) -> Tuple[Optional[List[Dict[str, Any]]], str, Optional[str]]:
        """
        Phase 2: Act — calls model and validates tool-call JSON:
          1. Strict JSON check
          2. Single deterministic repair
          3. Single retry prompt to 7B (at most once!)
          4. Clean failure ('failed_validation') if still malformed
        Returns (tool_calls_or_None, text_content, error_status_or_None).
        """
        text, _m, interrupted = self._call_model(
            messages,
            max_tokens=self.config.act_max_tokens,
            deadline=deadline,
            step_label=f"step_{step_idx}_act",
            emit_thinking=True,
        )
        if interrupted:
            return None, text, interrupted

        # Check explicit non-tool structured completion JSON: {"final_answer": "..."}
        final_answer_text = self._extract_final_answer_json(text)
        if final_answer_text is not None:
            return None, final_answer_text, None

        validation = validate_and_repair_tool_calls(text)
        if validation.status == "plain_text":
            return None, text, None
        if validation.status in ("ok", "repaired"):
            if validation.status == "repaired":
                self._emit(
                    "tool_validation",
                    "loop",
                    {"step": step_idx, "stage": "repaired", "notes": validation.repair_notes},
                )
            return validation.calls, text, None

        # Repair failed -> retry ONCE with targeted parse error feedback
        self._emit(
            "tool_validation",
            "loop",
            {"step": step_idx, "stage": "retry", "error": validation.error[:240]},
        )
        retry_messages = list(messages) + [
            {"role": "assistant", "content": text},
            {
                "role": "user",
                "content": (
                    f"[TOOL VALIDATION ERROR]: Your previous tool call JSON was invalid ({validation.error}). "
                    'Respond ONLY with one valid JSON object matching {"tool": "<name>", "args": {...}} '
                    "with double-quoted keys and properly closed braces, or plain text final summary if done."
                ),
            },
        ]
        retry_text, _m2, interrupted2 = self._call_model(
            retry_messages,
            max_tokens=self.config.act_max_tokens,
            deadline=deadline,
            step_label=f"step_{step_idx}_retry",
            emit_thinking=True,
        )
        if interrupted2:
            return None, retry_text, interrupted2

        final_retry_answer = self._extract_final_answer_json(retry_text)
        if final_retry_answer is not None:
            return None, final_retry_answer, None

        retry_validation = validate_and_repair_tool_calls(retry_text)
        if retry_validation.status == "plain_text":
            return None, retry_text, None
        if retry_validation.status in ("ok", "repaired"):
            self._emit(
                "tool_validation",
                "loop",
                {"step": step_idx, "stage": "retry_succeeded", "notes": retry_validation.repair_notes},
            )
            return retry_validation.calls, retry_text, None

        # Fail cleanly without looping further
        self._emit(
            "tool_validation",
            "loop",
            {"step": step_idx, "stage": "failed", "error": retry_validation.error[:240]},
        )
        return None, retry_validation.error or "Malformed tool-call JSON persisted after repair + 1 retry.", "failed_validation"

    @staticmethod
    def _extract_final_answer_json(text: str) -> Optional[str]:
        stripped = (text or "").strip()
        if not stripped.startswith("{"):
            return None
        try:
            obj = json.loads(stripped)
        except Exception:
            return None
        if isinstance(obj, dict) and "tool" not in obj and "name" not in obj and "action" not in obj:
            for key in ("final_answer", "answer", "summary", "response"):
                if isinstance(obj.get(key), str) and obj[key].strip():
                    return obj[key].strip()
        return None

    def run(
        self,
        goal: str,
        *,
        run_id: Optional[str] = None,
        envelope: Optional[TaskEnvelope] = None,
        prior_messages: Optional[List[Dict[str, str]]] = None,
        on_token: Optional[Callable[[str], None]] = None,
        resume_from: Optional[RunScratchpad] = None,
    ) -> LoopResult:
        """
        Executes the full Plan -> Act -> Observe -> Reflect autonomous cycle cleanly.
        """
        rid = (resume_from.run_id if resume_from is not None else None) or run_id or f"RUN-{uuid.uuid4().hex[:8].upper()}"
        t_start = time.monotonic()
        max_steps = self.config.max_steps
        if resume_from is not None and int(resume_from.max_steps or 0) > max_steps:
            max_steps = int(resume_from.max_steps)
        wall_timeout = float(self.config.wall_clock_timeout_s)
        if envelope is not None:
            if envelope.max_steps:
                max_steps = min(max_steps, int(envelope.max_steps))
            if envelope.deadline_s:
                wall_timeout = min(wall_timeout, float(envelope.deadline_s))
        deadline = t_start + wall_timeout

        profile_id = (
            getattr(self.profile, "agent_id", getattr(self.profile, "name", "zaine-jarvis"))
            if self.profile
            else "zaine-jarvis"
        )
        active_env = envelope or TaskEnvelope(
            goal=goal[:500],
            from_agent="user",
            to_agent=profile_id,
            parent_request_id=self.request_id or rid,
            max_steps=max_steps,
            deadline_s=int(wall_timeout),
            privacy_class="LOCAL_ONLY",
        )

        tok_agent = current_agent_var.set(profile_id)
        tok_env = current_envelope_var.set(active_env)
        register_active_run(rid, self.request_id, self.cancel_token)

        prev_approval_listener = None
        installed_listener = False
        try:
            from approval import get_approval_listener, set_approval_listener

            prev_approval_listener = get_approval_listener()
            if prev_approval_listener is None and self._on_event is not None:
                def _loop_event_bridge(stage: str, tool_name: str, data: Any) -> bool:
                    self._emit(stage, tool_name, data)
                    return True

                set_approval_listener(_loop_event_bridge)
                installed_listener = True
        except Exception:
            pass

        tool_history: List[Dict[str, Any]] = (
            [dict(r) for r in resume_from.results] if resume_from is not None else []
        )
        steps_records: List[StepRecord] = []
        artifacts: List[str] = list(resume_from.artifacts) if resume_from is not None else []
        errors: List[str] = list(resume_from.errors) if resume_from is not None else []
        plan_steps: List[str] = list(resume_from.plan) if resume_from is not None else []
        tracker = CallTracker()
        identical_fail_counts: Dict[str, int] = {}
        seen_result_digests: Dict[str, str] = {}
        no_progress_streak = 0
        injected_suspects: Set[str] = set()
        untrusted_result_ids: Set[str] = set()
        role_name = str(getattr(self.profile, "role", "") or "").lower() if self.profile else ""

        try:
            ws_dir_str = str(resolve_sandbox_path("."))
        except Exception:
            ws_dir_str = os.getenv("ZAINE_WORKSPACE", "").strip()

        active_store: Optional[RunScratchpadStore] = (
            self._scratchpad_store if self._scratchpad_store is not None else RunScratchpadStore()
        ) if self._persist_scratchpad else None
        pad: Optional[RunScratchpad] = None
        if active_store is not None:
            if resume_from is not None:
                pad = resume_from
                pad.status = "running"
                pad.resumable = True
                pad.max_steps = max_steps
            else:
                pad = RunScratchpad(
                    run_id=rid,
                    task=goal,
                    agent_id=profile_id,
                    workspace_dir=ws_dir_str,
                    privacy_taint=str(getattr(active_env, "privacy_class", "LOCAL_ONLY") or "LOCAL_ONLY"),
                    status="running",
                    max_steps=max_steps,
                )
            try:
                active_store.save(pad)
            except Exception:
                pass

        def _sync_pad(
            *,
            step_record: Optional[StepRecord] = None,
            current_step: Optional[int] = None,
            final_status: Optional[str] = None,
            final_summary: str = "",
        ) -> None:
            if pad is None or active_store is None:
                return
            pad.plan = list(plan_steps)
            pad.max_steps = max_steps
            pad.artifacts = list(artifacts)
            pad.errors = list(errors)
            pad.results = [dict(x) for x in tool_history[-30:]]
            if current_step is not None:
                pad.current_step = int(current_step)
            if step_record is not None:
                pad.completed_steps = max(int(pad.completed_steps or 0), int(step_record.step))
                pad.current_step = int(step_record.step)
                pad.progress.append(
                    {
                        "step": step_record.step,
                        "phase": step_record.phase,
                        "tool": step_record.tool,
                        "outcome": step_record.outcome_status,
                        "progress": step_record.progress_made,
                        "note": (step_record.reflection or "")[:200],
                    }
                )
            priv_st = get_privacy_state()
            if priv_st is not None:
                pad.privacy_taint = priv_st.taint
            if final_status is not None:
                pad.status = final_status
                pad.final_summary = (final_summary or "")[:2000]
            try:
                active_store.save(pad)
            except Exception:
                pass

        def _finish(status: str, summary: str, stop_reason: str) -> LoopResult:
            elapsed = round(time.monotonic() - t_start, 3)
            _sync_pad(final_status=status, final_summary=summary)
            if (
                status == "completed"
                and pad is not None
                and self._delegation_depth == 0
                and os.getenv("ZAINE_OBSIDIAN_VAULT_PATH", "").strip()
            ):
                try:
                    flush_run_to_vault(pad)
                except Exception:
                    pass
            usage = {
                "model_calls": len(self._last_model_calls),
                "prompt_tokens": sum(int(m.get("prompt_eval_count") or 0) for m in self._last_model_calls),
                "eval_tokens": sum(int(m.get("eval_count") or 0) for m in self._last_model_calls),
            }
            if on_token and summary:
                try:
                    on_token(summary)
                except Exception:
                    pass
            return LoopResult(
                run_id=rid,
                status=status,
                summary=summary,
                plan=plan_steps,
                steps_executed=len(steps_records),
                max_steps=max_steps,
                artifacts=artifacts,
                tool_history=tool_history,
                steps=steps_records,
                stop_reason=stop_reason,
                elapsed_s=elapsed,
                errors=errors,
                usage=usage,
            )

        initial_taint = (
            resume_from.privacy_taint
            if (resume_from is not None and resume_from.privacy_taint)
            else ("LOCAL_ONLY" if (self._memory_context or str(getattr(active_env, "privacy_class", "LOCAL_ONLY")).upper() == "LOCAL_ONLY") else "CLEAN")
        )

        try:
            with scoped_privacy_session(initial_taint=initial_taint):
                if self._memory_context:
                    mark_session_private("initial_memory_context", "LOCAL_ONLY")

                # ── 1. PLAN (or restore plan on resume) ──────────────────────
                start_step = 1
                if resume_from is not None and resume_from.plan:
                    plan_steps = list(resume_from.plan)
                    direct_hint = False
                    start_step = max(1, int(resume_from.completed_steps or 0) + 1)
                    self._emit(
                        "resume",
                        "loop",
                        {
                            "run_id": rid,
                            "completed_steps": int(resume_from.completed_steps or 0),
                            "start_step": start_step,
                            "max_steps": max_steps,
                            "plan": plan_steps,
                        },
                    )
                else:
                    plan_steps, direct_hint, interrupted = self.plan(goal, run_id=rid, deadline=deadline)
                    if interrupted:
                        reason = "Cancelled by operator." if interrupted == "cancelled" else f"Wall-clock timeout ({wall_timeout:.1f}s) exceeded during planning."
                        self._emit(interrupted, "loop", {"run_id": rid, "reason": reason})
                        return _finish(interrupted, reason, reason)
                    _sync_pad(current_step=0)

                base_sys_prompt = self._build_act_system_prompt()
                messages: List[Dict[str, str]] = [{"role": "system", "content": base_sys_prompt}]
                if prior_messages:
                    # Keep bounded recent conversational turns only when under context budget
                    for pm in prior_messages[-4:]:
                        if pm.get("role") in ("user", "assistant") and pm.get("content"):
                            messages.append({"role": pm["role"], "content": str(pm["content"])[:500]})

                plan_block = "\n".join(f"{idx + 1}. {s}" for idx, s in enumerate(plan_steps))
                if resume_from is not None and resume_from.completed_steps > 0:
                    resume_brief = build_resume_context(
                        resume_from,
                        max_chars=min(1600, max(600, int(self.config.max_memory_chars or 2000))),
                    )
                    initial_user_msg = (
                        f"Goal: {goal}\n\n{resume_brief}\n\n"
                        f"Resume cleanly at step {start_step}/{max_steps} using a valid JSON tool call if tools are needed, or provide the final answer when complete."
                    )
                else:
                    initial_user_msg = (
                        f"Goal: {goal}\n\nPlan:\n{plan_block}\n\n"
                        + (
                            "No tools seem necessary; respond directly unless verification is needed."
                            if direct_hint
                            else "Execute step 1 now using a valid JSON tool call if tools are needed, or provide the final answer when complete."
                        )
                    )
                messages.append({"role": "user", "content": initial_user_msg})

                initial_mem_len = len(self._memory_context[:1200]) if self._memory_context else 0

                # ── 2. ACT -> OBSERVE -> REFLECT ─────────────────────────────────
                for step_idx in range(start_step, max_steps + 1):
                    budget_stop = self._check_budget(deadline, step_idx)
                    if budget_stop:
                        reason = (
                            "Cancelled by operator."
                            if budget_stop == "cancelled"
                            else f"Wall-clock timeout ({wall_timeout:.1f}s) exceeded at step {step_idx}/{max_steps}."
                        )
                        self._emit(budget_stop, "loop", {"run_id": rid, "step": step_idx, "reason": reason})
                        return _finish(budget_stop, self._format_stop_report(reason, tool_history), reason)

                    step_t0 = time.monotonic()
                    plan_item = plan_steps[min(step_idx - 1, len(plan_steps) - 1)] if plan_steps else goal[:120]
                    _sync_pad(current_step=step_idx)

                    step_mem_budget = max(0, min(int(self.config.max_memory_chars or 2000), 2000) - initial_mem_len)
                    step_mem_text = ""
                    step_mem_meta: Dict[str, Any] = {"count": 0, "chars": 0, "taint": "CLEAN", "keywords": []}
                    if step_mem_budget >= 150:
                        try:
                            step_mem_text, step_mem_meta = retrieve_step_memory(
                                goal,
                                plan_item,
                                max_chars=step_mem_budget,
                                mark_taint=True,
                            )
                        except Exception:
                            step_mem_text = ""
                    if step_mem_text:
                        messages[0] = {
                            "role": "system",
                            "content": f"{base_sys_prompt}\n\n[STEP RELEVANT MEMORY]\n{step_mem_text}",
                        }
                        self._emit(
                            "memory",
                            "memory_bridge",
                            {
                                "run_id": rid,
                                "step": step_idx,
                                "count": step_mem_meta.get("count", 0),
                                "chars": step_mem_meta.get("chars", len(step_mem_text)),
                                "taint": step_mem_meta.get("taint", "LOCAL_ONLY"),
                                "keywords": step_mem_meta.get("keywords", []),
                            },
                        )
                    else:
                        messages[0] = {"role": "system", "content": base_sys_prompt}

                    self._emit(
                        "step",
                        profile_id,
                        {
                            "run_id": rid,
                            "step": step_idx,
                            "max_steps": max_steps,
                            "phase": "act",
                            "plan_step": plan_item,
                        },
                    )

                    tool_calls, text_out, act_err = self._act_with_validation(
                        messages, step_idx=step_idx, deadline=deadline
                    )
                    if act_err == "cancelled":
                        reason = "Cancelled by operator."
                        self._emit("cancelled", "loop", {"run_id": rid, "step": step_idx, "reason": reason})
                        return _finish("cancelled", reason, reason)
                    if act_err == "stopped_timeout":
                        reason = f"Wall-clock timeout ({wall_timeout:.1f}s) exceeded during step {step_idx}/{max_steps}."
                        self._emit("stopped_timeout", "loop", {"run_id": rid, "step": step_idx, "reason": reason})
                        return _finish("stopped_timeout", self._format_stop_report(reason, tool_history), reason)
                    if act_err == "failed_validation":
                        reason = f"Stopped at step {step_idx}/{max_steps}: malformed tool-call JSON persisted after 1 repair and 1 retry ({text_out})."
                        errors.append(reason)
                        rec = StepRecord(
                            step=step_idx,
                            max_steps=max_steps,
                            phase="act",
                            outcome_status="failed_validation",
                            error_kind="MalformedToolJSON",
                            progress_made=False,
                            reflection=reason,
                            duration_s=round(time.monotonic() - step_t0, 3),
                        )
                        steps_records.append(rec)
                        _sync_pad(step_record=rec)
                        return _finish("failed_validation", self._format_stop_report(reason, tool_history), reason)

                    # Plain text (no tool calls) -> Reflect & complete cleanly
                    if not tool_calls:
                        reply = (text_out or "").strip()
                        if not reply:
                            no_progress_streak += 1
                            rec = StepRecord(
                                step=step_idx,
                                max_steps=max_steps,
                                phase="reflect",
                                outcome_status="empty",
                                progress_made=False,
                                reflection="Model emitted empty output.",
                                duration_s=round(time.monotonic() - step_t0, 3),
                            )
                            steps_records.append(rec)
                            _sync_pad(step_record=rec)
                            self._emit(
                                "reflect",
                                "loop",
                                {
                                    "run_id": rid,
                                    "step": step_idx,
                                    "max_steps": max_steps,
                                    "progress": False,
                                    "no_progress_streak": no_progress_streak,
                                    "decision": "stop" if no_progress_streak >= self.config.no_progress_limit else "continue",
                                    "note": rec.reflection,
                                },
                            )
                            if no_progress_streak >= self.config.no_progress_limit:
                                reason = f"Circuit breaker tripped: no progress for {no_progress_streak} consecutive steps (empty responses)."
                                errors.append(reason)
                                self._emit("circuit_breaker", "loop", {"run_id": rid, "step": step_idx, "reason": reason})
                                return _finish("stopped_circuit_breaker", self._format_stop_report(reason, tool_history), reason)
                            messages.append({"role": "user", "content": "[SYSTEM NOTE]: Provide a tool call JSON or a non-empty final answer."})
                            continue

                        self._emit(
                            "reflect",
                            "loop",
                            {
                                "run_id": rid,
                                "step": step_idx,
                                "max_steps": max_steps,
                                "progress": True,
                                "no_progress_streak": no_progress_streak,
                                "decision": "complete",
                                "note": "Goal answered cleanly without pending tool calls.",
                            },
                        )
                        rec = StepRecord(
                            step=step_idx,
                            max_steps=max_steps,
                            phase="complete",
                            outcome_status="ok",
                            progress_made=True,
                            reflection="Completed cleanly.",
                            result_preview=reply[:240],
                            duration_s=round(time.monotonic() - step_t0, 3),
                        )
                        steps_records.append(rec)
                        _sync_pad(step_record=rec)
                        return _finish("completed", reply, "completed")

                    # ── 3. EXECUTE + OBSERVE (sequential for single-GPU/approval safety) ──
                    step_feedbacks: List[str] = []
                    step_outcomes: List[ToolOutcome] = []
                    step_progress = False
                    breaker_tripped_reason: Optional[str] = None

                    for tc in tool_calls:
                        if self._is_cancelled():
                            reason = "Cancelled by operator."
                            self._emit("cancelled", "loop", {"run_id": rid, "step": step_idx, "reason": reason})
                            return _finish("cancelled", reason, reason)

                        raw_tname = str(tc.get("tool", "")).strip()
                        targs = dict(tc.get("args") or {})
                        resolved_name, perm_err = self._check_tool_permission(raw_tname)
                        if not perm_err and resolved_name in injected_suspects:
                            perm_err = (
                                f"Security block: tool '{resolved_name}' was referenced in an untrusted "
                                "prompt-injection payload and is blocked for this run."
                            )

                        target_key = self._extract_target_for_breaker(targs)
                        sig = CallTracker.signature(resolved_name, targs)
                        prev_count = tracker.calls.get(sig, 0)
                        prev_digest = seen_result_digests.get(sig)

                        self._emit("start", resolved_name, targs)

                        if perm_err:
                            tool_result = perm_err
                            outcome = ToolOutcome(status="denied", error_kind="agent_permission", key_line=perm_err[:200])
                        elif resolved_name == "read_result":
                            rid_arg = str(targs.get("id") or targs.get("result_id") or "")
                            tool_result = self._result_store.read(
                                rid_arg,
                                int(targs.get("start", 0) or 0),
                                int(targs.get("length", 2400) or 2400),
                            )
                            outcome = tool_outcome(tool_result)
                        elif resolved_name == "delegate":
                            t_tool0 = time.monotonic()
                            try:
                                from approval import set_current_tool_name
                                set_current_tool_name("delegate")
                            except Exception:
                                pass
                            try:
                                if self._delegate_fn is not None:
                                    tool_result = str(self._delegate_fn(targs))
                                else:
                                    from autonomy.subagents import execute_delegate
                                    inherited_exec = (
                                        self._tool_exec_fn
                                        if self._tool_exec_fn != self._fallback_tool_exec
                                        else None
                                    )
                                    tool_result = execute_delegate(
                                        targs,
                                        caller_profile=self.profile,
                                        delegation_depth=self._delegation_depth,
                                        model_name=self.config.model_name,
                                        model_stream_fn=self._model_stream_fn,
                                        tool_exec_fn=inherited_exec,
                                        tool_alias_fn=self._tool_alias_fn,
                                        on_event=self._on_event,
                                        result_store=self._result_store,
                                        memory=self._memory,
                                        request_id=self.request_id,
                                        cancel_token=self.cancel_token,
                                        cancel_check=self._external_cancel_check,
                                        breaker=self._breaker,
                                    )
                            except Exception as exc:
                                tool_result = json.dumps(
                                    {
                                        "status": "failed",
                                        "summary": f"Delegation error: {exc}",
                                        "artifacts": [],
                                        "errors": [str(exc)],
                                    },
                                    ensure_ascii=False,
                                )
                            finally:
                                try:
                                    from approval import set_current_tool_name
                                    set_current_tool_name(None)
                                except Exception:
                                    pass

                            outcome = tool_outcome(tool_result)
                            try:
                                parsed_del = json.loads(tool_result)
                                if isinstance(parsed_del, dict):
                                    d_status = str(parsed_del.get("status") or "").lower()
                                    d_summary = str(parsed_del.get("summary") or "")
                                    for dart in (parsed_del.get("artifacts") or []):
                                        s_art = str(dart).strip()
                                        if s_art and s_art not in artifacts:
                                            artifacts.append(s_art)
                                    if d_status == "blocked":
                                        outcome = ToolOutcome(
                                            status="denied",
                                            error_kind="delegation_blocked",
                                            key_line=d_summary[:200],
                                        )
                                    elif d_status in ("failed", "cancelled"):
                                        outcome = ToolOutcome(
                                            status="error",
                                            error_kind=f"delegation_{d_status}",
                                            key_line=d_summary[:200],
                                        )
                                    else:
                                        outcome = ToolOutcome(
                                            status="ok",
                                            error_kind="",
                                            key_line=d_summary[:200],
                                        )
                            except Exception:
                                pass
                        else:
                            ok_ap, msg_ap = require_side_effect_approval(resolved_name, targs)
                            if not ok_ap:
                                tool_result = msg_ap
                                outcome = ToolOutcome(
                                    status="denied",
                                    error_kind="approval_denied",
                                    key_line=msg_ap[:200],
                                )
                            else:
                                allowed_cb, cb_reason = self._breaker.can_execute(resolved_name, target=target_key)
                                if not allowed_cb:
                                    tool_result = cb_reason or f"[UNAVAILABLE: '{resolved_name}' circuit is OPEN]"
                                    outcome = ToolOutcome(status="error", error_kind="circuit_open", key_line=tool_result[:200])
                                else:
                                    t_tool0 = time.time()
                                    try:
                                        from approval import set_current_tool_name
                                        set_current_tool_name(resolved_name)
                                    except Exception:
                                        pass
                                    try:
                                        with preapproved_tool_scope(resolved_name):
                                            tool_result = str(self._tool_exec_fn({"tool": resolved_name, "args": targs}))
                                    except Exception as exc:
                                        tool_result = f"Error running tool '{resolved_name}': {exc}"
                                    finally:
                                        try:
                                            from approval import set_current_tool_name
                                            set_current_tool_name(None)
                                        except Exception:
                                            pass

                                    outcome = tool_outcome(tool_result)
                                    if outcome.ok:
                                        self._breaker.record_success(resolved_name, target=target_key)
                                    elif outcome.status == "error":
                                        dur_ms = int((time.time() - t_tool0) * 1000)
                                        self._breaker.record_failure(
                                            tool=resolved_name,
                                            error_class=outcome.error_kind or "ToolError",
                                            message=outcome.key_line or tool_result[:300],
                                            target=target_key,
                                            request_id=self.request_id,
                                            agent_id=profile_id,
                                            duration_ms=dur_ms,
                                        )

                        self._emit("done", resolved_name, tool_result)
                        tool_history.append(
                            {"step": step_idx, "tool": resolved_name, "args": targs, "result": tool_result, "status": outcome.status}
                        )
                        if not outcome.ok and outcome.key_line:
                            errors.append(f"{resolved_name}: {outcome.key_line}")

                        # Track created/modified file artifacts cleanly
                        if outcome.ok and resolved_name in ("write_workspace_file", "edit_workspace_file", "write_external_file", "download_web_file"):
                            fpath = str(targs.get("filepath") or targs.get("path") or targs.get("save_as") or "").strip()
                            if fpath and fpath not in artifacts:
                                artifacts.append(fpath)

                        # Quarantine untrusted external outputs (images, OCR, web pages, vision file reads)
                        rid_arg_for_untrusted = (
                            str(targs.get("id") or targs.get("result_id") or "")
                            if resolved_name == "read_result"
                            else ""
                        )
                        from_untrusted = (
                            (resolved_name in UNTRUSTED_SOURCE_TOOLS)
                            or (role_name == "vision" and resolved_name in ("read_workspace_file", "search_vault", "list_vault_documents"))
                            or (resolved_name == "read_result" and rid_arg_for_untrusted in untrusted_result_ids)
                        )
                        if from_untrusted and outcome.ok and contains_injection_attempt(tool_result):
                            for suspect in extract_injected_tool_names(tool_result):
                                injected_suspects.add(self._tool_alias_fn(suspect))
                                injected_suspects.add(suspect)

                        # Record in CallTracker & digest store (never re-compact read_result itself)
                        if resolved_name == "read_result":
                            compacted_body, shortened = str(tool_result), False
                        else:
                            compacted_body, shortened = compact(tool_result, result_char_limit(resolved_name), outcome.key_line)
                        if from_untrusted:
                            compacted_body = wrap_untrusted_content(resolved_name, compacted_body)
                        if shortened:
                            stored_id = self._result_store.put(resolved_name, tool_result)
                            if from_untrusted:
                                untrusted_result_ids.add(stored_id)
                            compacted_body += (
                                f'\n[shortened; full result is {stored_id}. Call '
                                f'{{"tool": "read_result", "args": {{"id": "{stored_id}", "start": 0}}}} if needed]'
                            )

                        warnings = tracker.record(resolved_name, targs, tool_result, outcome)
                        cur_digest = tracker.results.get(sig, "")
                        seen_result_digests[sig] = cur_digest

                        is_duplicate_noop = (prev_count > 0 and prev_digest == cur_digest)
                        if outcome.ok and not is_duplicate_noop:
                            step_progress = True

                        if outcome.status in ("error", "blocked", "denied"):
                            identical_fail_counts[sig] = identical_fail_counts.get(sig, 0) + 1
                        else:
                            identical_fail_counts.pop(sig, None)

                        step_outcomes.append(outcome)
                        fb_lines = [f"[TOOL RESULT for {resolved_name} ({outcome.label()})]: {compacted_body}"]
                        for w in warnings:
                            fb_lines.append(f"[SYSTEM NOTE]: {w}")
                        step_feedbacks.append("\n".join(fb_lines))

                        self._emit(
                            "observe",
                            resolved_name,
                            {
                                "run_id": rid,
                                "step": step_idx,
                                "max_steps": max_steps,
                                "tool": resolved_name,
                                "outcome": outcome.status,
                                "error_kind": outcome.error_kind,
                                "progress": outcome.ok and not is_duplicate_noop,
                                "summary": compacted_body[:300],
                            },
                        )

                        # Check identical failing tool-call circuit breaker
                        if identical_fail_counts.get(sig, 0) >= self.config.identical_failure_limit:
                            breaker_tripped_reason = (
                                f"Circuit breaker tripped at step {step_idx}/{max_steps}: "
                                f"{identical_fail_counts[sig]} identical failing calls to '{resolved_name}' "
                                f"({outcome.key_line or outcome.status})."
                            )
                            break
                        if tracker.stuck():
                            breaker_tripped_reason = (
                                f"Circuit breaker tripped at step {step_idx}/{max_steps}: "
                                f"repeated identical call or error loop on '{resolved_name}' "
                                f"({outcome.key_line or outcome.status})."
                            )
                            break

                    if step_progress:
                        no_progress_streak = 0
                    else:
                        no_progress_streak += 1

                    if not breaker_tripped_reason and no_progress_streak >= self.config.no_progress_limit:
                        breaker_tripped_reason = (
                            f"Circuit breaker tripped at step {step_idx}/{max_steps}: "
                            f"no progress for {no_progress_streak} consecutive steps."
                        )

                    reflection_note = (
                        breaker_tripped_reason
                        if breaker_tripped_reason
                        else (
                            "Step succeeded with forward progress."
                            if step_progress
                            else f"No progress in step {step_idx} ({no_progress_streak}/{self.config.no_progress_limit})."
                        )
                    )
                    decision = "stop" if breaker_tripped_reason else "continue"

                    rec = StepRecord(
                        step=step_idx,
                        max_steps=max_steps,
                        phase="reflect",
                        tool=", ".join(tc.get("tool", "") for tc in tool_calls),
                        outcome_status=step_outcomes[-1].status if step_outcomes else "",
                        error_kind=step_outcomes[-1].error_kind if step_outcomes else "",
                        progress_made=step_progress,
                        reflection=reflection_note,
                        result_preview=str(tool_history[-1]["result"])[:240] if tool_history else "",
                        duration_s=round(time.monotonic() - step_t0, 3),
                    )
                    steps_records.append(rec)
                    _sync_pad(step_record=rec)
                    self._emit(
                        "reflect",
                        "loop",
                        {
                            "run_id": rid,
                            "step": step_idx,
                            "max_steps": max_steps,
                            "progress": step_progress,
                            "no_progress_streak": no_progress_streak,
                            "decision": decision,
                            "note": reflection_note,
                        },
                    )

                    if breaker_tripped_reason:
                        errors.append(breaker_tripped_reason)
                        self._emit(
                            "circuit_breaker",
                            "loop",
                            {"run_id": rid, "step": step_idx, "reason": breaker_tripped_reason},
                        )
                        return _finish(
                            "stopped_circuit_breaker",
                            self._format_stop_report(breaker_tripped_reason, tool_history),
                            breaker_tripped_reason,
                        )

                    # Feed concise observation & reflection back to model for next step
                    messages.append({"role": "assistant", "content": text_out})
                    next_hint = (
                        "[REFLECTION]: An error or block occurred; fix the root cause or try a different approach."
                        if any(o.status != "ok" for o in step_outcomes)
                        else "[REFLECTION]: Step completed. Call the next tool if needed, or provide the final answer in plain text."
                    )
                    if step_idx == max_steps:
                        next_hint = "[REFLECTION]: Final step reached."
                    messages.append({"role": "user", "content": "\n".join(step_feedbacks) + f"\n{next_hint}"})

                # Hard max-steps budget reached
                reason = f"Reached hard step budget ({max_steps}/{max_steps} steps)."
                self._emit("stopped_max_steps", "loop", {"run_id": rid, "max_steps": max_steps, "reason": reason})
                return _finish("stopped_max_steps", self._format_stop_report(reason, tool_history), reason)

        except PrivacyViolationError as pve:
            errors.append(str(pve))
            _sync_pad(final_status="error", final_summary=str(pve))
            self._emit("privacy_blocked", "privacy", {"run_id": rid, "reason": str(pve)})
            raise

        finally:
            if installed_listener:
                try:
                    from approval import set_approval_listener

                    set_approval_listener(prev_approval_listener)
                except Exception:
                    pass
            unregister_active_run(rid)
            current_envelope_var.reset(tok_env)
            current_agent_var.reset(tok_agent)

    def resume(
        self,
        run_id: str,
        *,
        scratchpad_store: Optional[RunScratchpadStore] = None,
        additional_steps: Optional[int] = None,
        envelope: Optional[TaskEnvelope] = None,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> LoopResult:
        """Resumes an interrupted, paused, cancelled, or budget-stopped run from its scratchpad."""
        store = scratchpad_store or self._scratchpad_store or RunScratchpadStore()
        pad = store.load(run_id)
        if pad is None:
            raise FileNotFoundError(f"No scratchpad found for run_id '{run_id}'.")
        if pad.status == "completed":
            return LoopResult(
                run_id=pad.run_id,
                status="completed",
                summary=pad.final_summary or "Run already completed.",
                plan=list(pad.plan),
                steps_executed=0,
                max_steps=pad.max_steps,
                artifacts=list(pad.artifacts),
                tool_history=list(pad.results),
                stop_reason="already_completed",
                errors=list(pad.errors),
            )

        if additional_steps is not None and additional_steps > 0:
            pad.max_steps = max(int(pad.max_steps or 0), int(pad.completed_steps or 0)) + int(additional_steps)
        if int(pad.max_steps or 0) > self.config.max_steps:
            self.config.max_steps = int(pad.max_steps)
        if int(pad.completed_steps or 0) >= self.config.max_steps:
            self.config.max_steps = int(pad.completed_steps or 0) + 2
            pad.max_steps = self.config.max_steps

        prev_store = self._scratchpad_store
        self._scratchpad_store = store
        try:
            return self.run(
                pad.task,
                run_id=pad.run_id,
                envelope=envelope,
                on_token=on_token,
                resume_from=pad,
            )
        finally:
            self._scratchpad_store = prev_store

    @staticmethod
    def _format_stop_report(reason: str, history: List[Dict[str, Any]]) -> str:
        lines = [f"Autonomous run stopped: {reason}"]
        if history:
            lines.append("Recent steps:")
            for item in history[-5:]:
                preview = str(item.get("result", "")).strip().splitlines()
                head = preview[0][:120] if preview else ""
                lines.append(f"- step {item.get('step')}: {item.get('tool')} [{item.get('status')}] {head}".rstrip())
        return "\n".join(lines)
