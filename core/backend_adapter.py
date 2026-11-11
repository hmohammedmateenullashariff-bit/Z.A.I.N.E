"""
core/backend_adapter.py
Pluggable Inference Backend Abstraction for Z.A.I.N.E.

Supports:
1. OllamaBackend (Default, localhost:11434, native /api/chat & /api/generate)
2. LlamaCppServerBackend (localhost:8080, OpenAI-compatible /v1/chat/completions)

Enables switching inference engine via ZAINE_BACKEND environment variable
without modifying agent reasoning loops or tool execution logic.
"""

import os
import json
import time
import requests
from typing import Any, Dict, Generator, List, Optional


class InferenceBackend:
    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        options: Optional[Dict[str, Any]] = None,
        keep_alive: Any = -1,
    ) -> Generator[Dict[str, Any], None, None]:
        raise NotImplementedError

    def is_alive(self) -> bool:
        raise NotImplementedError

    def list_models(self) -> List[str]:
        raise NotImplementedError


class OllamaBackend(InferenceBackend):
    def __init__(self, base_url: str = "http://127.0.0.1:11434"):
        self.base_url = base_url.rstrip("/")

    def is_alive(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=2.0)
            if r.status_code == 200:
                data = r.json()
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            pass
        return []

    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        options: Optional[Dict[str, Any]] = None,
        keep_alive: Any = -1,
    ) -> Generator[Dict[str, Any], None, None]:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": keep_alive,
            "options": options or {},
        }
        with requests.post(url, json=payload, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        yield chunk
                    except Exception:
                        continue


class LlamaCppServerBackend(InferenceBackend):
    """
    Adapter for llama-server.exe running with OpenAI-compatible API.
    Compatible with: llama-server --port 8080 -m <model.gguf>
    """
    def __init__(self, base_url: str = "http://127.0.0.1:8080"):
        self.base_url = base_url.rstrip("/")

    def is_alive(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=2.0)
            return r.status_code == 200
        except Exception:
            try:
                r = requests.get(f"{self.base_url}/v1/models", timeout=2.0)
                return r.status_code == 200
            except Exception:
                return False

    def list_models(self) -> List[str]:
        try:
            r = requests.get(f"{self.base_url}/v1/models", timeout=2.0)
            if r.status_code == 200:
                data = r.json()
                return [m.get("id", "") for m in data.get("data", [])]
        except Exception:
            pass
        return ["default"]

    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        options: Optional[Dict[str, Any]] = None,
        keep_alive: Any = -1,
    ) -> Generator[Dict[str, Any], None, None]:
        url = f"{self.base_url}/v1/chat/completions"
        opts = options or {}
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": opts.get("num_predict", 512),
            "temperature": opts.get("temperature", 0.7),
        }
        with requests.post(url, json=payload, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8").strip()
                if decoded.startswith("data: "):
                    body = decoded[len("data: "):].strip()
                    if body == "[DONE]":
                        break
                    try:
                        chunk = json.loads(body)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        # Map to Ollama format: {"message": {"content": ...}}
                        yield {"message": {"content": content}, "done": False}
                    except Exception:
                        continue


def get_inference_backend() -> InferenceBackend:
    """Returns the backend determined by ZAINE_BACKEND environment variable."""
    backend_name = os.getenv("ZAINE_BACKEND", "ollama").lower().strip()
    if backend_name in ("llamacpp", "llama_server", "llama.cpp"):
        port = os.getenv("LLAMA_SERVER_PORT", "8080")
        return LlamaCppServerBackend(f"http://127.0.0.1:{port}")
    return OllamaBackend()

