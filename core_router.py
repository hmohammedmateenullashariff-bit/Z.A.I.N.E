"""
Z.A.I.N.E — Tiered Dual-Brain Core Router (Jarvis Low-Latency Architecture)
Implements:
1. Tier 0 (Reflex Brain): qwen2.5:3b (Pinned 100% in GPU VRAM, keep_alive=-1, 38.7 tokens/s)
2. Tier 1 (Deep Brain): qwen2.5:7b / zaine-coder (Deep architectural reasoning)
3. Vision Node: moondream:latest (Multimodal desktop perception)
4. Instant Verbal Acknowledgment Pipeline (< 400ms feedback before deep tasks)
5. Parallel Async Tool Dispatcher (concurrent.futures ThreadPool)
"""

import time
import json
import requests
from typing import Dict, Any, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from tool_clusters import classify_intent_clusters, build_clustered_system_prompt

OLLAMA_URL = "http://localhost:11434/api/chat"

REFLEX_MODEL = "qwen2.5:3b"
DEEP_MODEL = "deepseek-r1:7b"
CODER_MODEL = "qwen2.5-coder:3b"
VISION_MODEL = "moondream:latest"

# Thread pool for non-blocking parallel tool execution
_tool_executor = ThreadPoolExecutor(max_workers=4)


class TieredBrainRouter:
    """Orchestrates Tier 0 (Reflex) and Tier 1 (Deep) cognition for sub-second responses."""

    def __init__(self):
        self.reflex_model = REFLEX_MODEL
        self.deep_model = DEEP_MODEL
        self.coder_model = CODER_MODEL
        self.pinned_warm = False
        self._installed_cache = set()
        self._last_cache_check = 0

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
        if requested_model in installed:
            return requested_model
        # Check matching prefix (e.g. 'deepseek-r1' matches 'deepseek-r1:7b')
        for inst in installed:
            if requested_model.split(":")[0] in inst:
                return inst
        # Safe fallback to Reflex Core
        return self.reflex_model

    def pin_reflex_in_vram(self) -> bool:
        """Sends a zero-shot ping with keep_alive=-1 to permanently lock Tier 0 into VRAM."""
        try:
            payload = {
                "model": self.reflex_model,
                "messages": [{"role": "system", "content": "system online"}],
                "stream": False,
                "keep_alive": -1,
                "options": {"num_predict": 1}
            }
            resp = requests.post(OLLAMA_URL, json=payload, timeout=10)
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

        # Check deep coding triggers
        code_heavy = [
            "write a full", "architect", "refactor this system", "build a complete",
            "debug this complex", "implement the following algorithm", "system design",
            "deep dive", "ponytail architecture"
        ]
        if any(phrase in lower for phrase in code_heavy):
            return "DEEP_CODE"

        # Check deep reasoning
        if any(w in lower for w in ["explain in detail", "analyze the trade-offs", "comprehensive report"]):
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
