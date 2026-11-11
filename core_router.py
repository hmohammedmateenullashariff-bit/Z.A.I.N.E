"""
Z.A.I.N.E — Tiered Dual-Brain Core Router (Jarvis Low-Latency Architecture)
Implements:
1. Tier 0 (Reflex Brain): qwen2.5:3b (Pinned 100% in GPU VRAM, keep_alive=-1, 38.7 tokens/s)
2. Tier 1 (Deep Brain): qwen2.5:7b / zaine-coder (Deep architectural reasoning)
3. Vision Node: moondream:latest (Multimodal desktop perception)
4. Instant Verbal Acknowledgment Pipeline (< 400ms feedback before deep tasks)
5. Parallel Async Tool Dispatcher (concurrent.futures ThreadPool)
"""

import os
import time
import json
import requests
from typing import Dict, Any, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from tool_clusters import classify_intent_clusters, build_clustered_system_prompt

OLLAMA_URL = "http://localhost:11434/api/chat"

ZAINE_FAST = os.getenv("ZAINE_FAST", "1").lower() in ("1", "true", "yes")
ZAINE_SINGLE_MODEL = os.getenv("ZAINE_SINGLE_MODEL", "1").lower() in ("1", "true", "yes")

REFLEX_MODEL = "zaine-fast-3b" if ZAINE_FAST else "zaine-reflex-7b"
DEEP_MODEL = "zaine-reflex-7b" if not ZAINE_FAST else "zaine-coder-7b"
CODER_MODEL = "zaine-coder-7b"
VISION_MODEL = "moondream:latest"

# Thread pool for non-blocking parallel tool execution
_tool_executor = ThreadPoolExecutor(max_workers=4)


class TieredBrainRouter:
    """Orchestrates Tier 0 (Reflex) and Tier 1 (Deep) cognition for sub-second responses."""

    def __init__(self):
        self.pinned_warm = False
        self._installed_cache = set()
        self._last_cache_check = 0

    @property
    def fast_mode(self) -> bool:
        return os.getenv("ZAINE_FAST", "1").lower() in ("1", "true", "yes")

    @property
    def single_model(self) -> bool:
        return os.getenv("ZAINE_SINGLE_MODEL", "1").lower() in ("1", "true", "yes")

    @property
    def reflex_model(self) -> str:
        return "zaine-fast-3b" if self.fast_mode else REFLEX_MODEL

    @property
    def deep_model(self) -> str:
        return "zaine-coder-7b" if not self.single_model else self.reflex_model

    @property
    def coder_model(self) -> str:
        return CODER_MODEL

    def get_installed_models(self) -> set:
        """Fetches installed Ollama models with a 15-second cache to prevent spamming."""
        now = time.time()
        if now - self._last_cache_check > 15:
            try:
                r = requests.get("http://localhost:11434/api/tags", timeout=3)
                if r.status_code == 200:
                    self._installed_cache = {m.get("name") for m in r.json().get("models", [])}
                    self._last_cache_check = now
            except Exception:
                pass
        return self._installed_cache

    def resolve_model(self, requested_model: str) -> str:
        """Gracefully resolves model to installed weights, preventing 404 crashes."""
        installed = self.get_installed_models()
        if not installed:
            return requested_model

        if requested_model in installed:
            return requested_model
        if f"{requested_model}:latest" in installed:
            return f"{requested_model}:latest"

        # Fallback hierarchy for 7B models (3B models purged)
        fallbacks = {
            "zaine-fast-3b": ["zaine-fast-3b:latest", "qwen2.5:3b"],
            "zaine-coder-7b": ["zaine-coder-7b:latest", "qwen2.5-coder:7b-instruct-q3_K_M", "qwen2.5-coder:7b", "zaine-reflex-7b:latest"],
            "zaine-reflex-7b": ["zaine-reflex-7b:latest", "qwen2.5:7b-instruct-q3_K_M", "qwen2.5:7b"],
            "deepseek-r1:7b": ["deepseek-r1:7b", "zaine-reflex-7b:latest", "qwen2.5:7b-instruct-q3_K_M"],
        }
        for fb in fallbacks.get(requested_model, []):
            if fb in installed:
                return fb
            if f"{fb}:latest" in installed:
                return f"{fb}:latest"

        # Check matching prefix (e.g. 'deepseek-r1' matches 'deepseek-r1:7b')
        req_prefix = requested_model.split(":")[0].lower()
        for inst in installed:
            if req_prefix in inst.lower():
                return inst

        # Prefer zaine-reflex-7b or qwen2.5-7b
        for pref in ["zaine-reflex-7b:latest", "qwen2.5:7b-instruct-q3_K_M", "qwen2.5:7b"]:
            if pref in installed:
                return pref
        # Safe fallback: return the first available model that is not an embed model
        for inst in installed:
            if "embed" not in inst.lower():
                return inst
        return next(iter(installed)) if installed else self.reflex_model

    def pin_reflex_in_vram(self) -> bool:
        """Sends a zero-shot ping with keep_alive=-1 to permanently lock Tier 0 into VRAM."""
        try:
            num_ctx_val = int(os.environ.get("ZAINE_NUM_CTX", "4096"))
            options_dict = {"num_ctx": num_ctx_val, "num_predict": 1}
            effective_model = self.resolve_model(self.reflex_model)
            payload = {
                "model": effective_model,
                "messages": [{"role": "system", "content": "system online"}],
                "stream": False,
                "keep_alive": -1,
                "options": options_dict
            }
            t0 = time.perf_counter()
            resp = requests.post(OLLAMA_URL, json=payload, timeout=10)
            wall_time = time.perf_counter() - t0
            raw_json = resp.json() if resp.status_code == 200 else {}
            try:
                from ollama_profiler import log_ollama_call
                log_ollama_call(
                    caller="core_router.pin_reflex_in_vram",
                    model=self.reflex_model,
                    options=options_dict,
                    response_data=raw_json,
                    wall_time_s=wall_time,
                    keep_alive=-1,
                )
            except Exception:
                pass
            self.pinned_warm = (resp.status_code == 200)
            return self.pinned_warm
        except Exception:
            return False

    def classify_task_tier(self, prompt: str) -> str:
        """
        Classifies task complexity into:
        - 'REFLEX': General conversation, system status, volume, weather, simple tasks.
        - 'VISION': Screen or camera perception.
        - 'DEEP_CODE': Complex multi-file coding, algorithmic design, debugging.
        - 'DEEP_REASONING': Architectural analysis, comprehensive planning.
        """
        lower = prompt.lower()

        # Check vision triggers
        if any(w in lower for w in ["screen", "look at my screen", "camera", "webcam", "see screen", "inspect screen", "what do you see"]):
            return "VISION"

        # Check deep coding, pipelines, media automation, and tool execution triggers
        code_heavy = [
            "write a full", "architect", "refactor this system", "build a complete",
            "debug this complex", "implement the following algorithm", "system design",
            "deep dive", "ponytail architecture", "pipeline", "youtube pipeline",
            "upload new content", "uploading new content", "generate video", "edit video",
            "reverse engineer", "scaffold website", "create tool", "delete_workspace_files",
            "start our youtube", "start the youtube"
        ]
        if any(phrase in lower for phrase in code_heavy):
            return "DEEP_CODE"

        # Check deep reasoning & workflow orchestration
        reasoning_heavy = [
            "explain in detail", "analyze the trade-offs", "comprehensive report",
            "orchestrate", "workflow", "plan phase", "execute phase", "verify work"
        ]
        if any(w in lower for w in reasoning_heavy):
            return "DEEP_REASONING"

        return "REFLEX"

    def get_instant_acknowledgment(self, task_tier: str, prompt: str, ultron_mode: bool = False) -> Optional[str]:
        """
        Generates immediate verbal feedback (< 300ms) for heavy or visual tasks
        so the user never hears awkward dead silence.
        """
        if task_tier == "VISION":
            return "Analyzing your screen right now, Creator." if ultron_mode else "Inspecting your screen now, Sir..."
        elif task_tier == "DEEP_CODE":
            return "Engaging deep code synthesis. Stand by, Creator." if ultron_mode else "Deliberating through the architecture now, Sir..."
        elif task_tier == "DEEP_REASONING":
            return "Processing multi-layer cognitive analysis." if ultron_mode else "Analyzing the parameters in depth now, Sir..."
        return None

    def execute_tools_parallel(self, tool_calls: List[Dict[str, Any]], executor_fn: Callable[[Dict[str, Any]], str]) -> List[Dict[str, Any]]:
        """Executes multiple tool calls concurrently rather than sequentially."""
        if len(tool_calls) == 1:
            # Fast path: single tool execution
            res = executor_fn(tool_calls[0])
            return [{"call": tool_calls[0], "result": res}]

        results = []
        future_map = {
            _tool_executor.submit(executor_fn, tc): tc
            for tc in tool_calls
        }
        for future in as_completed(future_map):
            tc = future_map[future]
            try:
                out = future.result()
            except Exception as e:
                out = f"Execution error in {tc.get('tool')}: {e}"
            results.append({"call": tc, "result": out})

        return results


# Global singleton instance
router = TieredBrainRouter()
