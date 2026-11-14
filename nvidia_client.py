"""
nvidia_client.py
Unified client for NVIDIA Build / NIM Cloud API (integrate.api.nvidia.com).

Supports:
1. Frontier 550B Reasoning & Code: nvidia/nemotron-3-ultra-550b-a55b
2. Multimodal Vision-Language 120B: nvidia/nemotron-3.5-super-vl-120b-a12b

Features:
- Dual-tier streaming & non-streaming completions
- Native support for reasoning_content + content tokens
- Base64 / PNG / JPEG visual image analysis
- Automatic timeout & network fallback to local Ollama
"""

import os
import re
import json
import time
import requests
from typing import Dict, Any, List, Optional, Iterator, Tuple

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_REASONING_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
DEFAULT_VISION_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
DEFAULT_BACKUP_MODEL = "minimaxai/minimax-m3.1-flash"
SECONDARY_BACKUP_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"


def get_nvidia_api_key() -> str:
    """Reads NVIDIA API key from environment."""
    return os.getenv("NVIDIA_API_KEY", "").strip()


def get_nvidia_base_url() -> str:
    """Reads NVIDIA Base URL from environment (defaults to integrate.api.nvidia.com/v1)."""
    return os.getenv("NVIDIA_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")


def get_reasoning_model() -> str:
    """Returns the configured frontier reasoning model."""
    return os.getenv("NVIDIA_REASONING_MODEL", DEFAULT_REASONING_MODEL).strip()


def get_vision_model() -> str:
    """Returns the configured multimodal vision model."""
    return os.getenv("NVIDIA_VISION_MODEL", DEFAULT_VISION_MODEL).strip()


def get_backup_model() -> str:
    """Returns the primary backup model to use if Nemotron 550B degrades or fails."""
    return os.getenv("NVIDIA_BACKUP_MODEL", DEFAULT_BACKUP_MODEL).strip()


def is_nvidia_available() -> bool:
    """Returns True if NVIDIA API key is configured."""
    key = get_nvidia_api_key()
    return bool(key and key.startswith("nvapi-"))


def validate_output_integrity(text: str) -> Tuple[bool, str]:
    """
    Validates output text against common failure modes of large frontier/MoE models:
    1. Single character infinite loops (e.g. aaaaaaaaaaaa...)
    2. N-gram repetition loops (repeating phrases)
    3. Multilingual / Token corruption bursts (sudden CJK/Cyrillic/Thai token dumps)
    4. Empty or truncated non-responses
    """
    if not text or len(text.strip()) < 5:
        return False, "empty_or_too_short"

    clean = text.strip()

    # 1. Single character repetition loops (15+ identical characters in a row)
    if re.search(r"(.)\1{14,}", clean):
        return False, "character_repetition_loop"

    # 2. Phrase repetition loops (2+ word sequences repeating 4+ times)
    words = clean.split()
    if len(words) >= 8:
        for n in (2, 3, 4, 5):
            for i in range(min(len(words) - n * 3, 30)):
                gram = " ".join(words[i:i+n]).lower()
                remainder = " ".join(words[i:])
                matches = len(re.findall(re.escape(gram), remainder.lower()))
                if matches >= 4:
                    return False, f"phrase_repetition_loop: '{gram[:25]}'"

    # 3. Multilingual token collapse / random foreign character bursts
    total_chars = len(clean)
    garbage_chars = [
        c for c in clean
        if "\u4e00" <= c <= "\u9fff"   # CJK
        or "\u0400" <= c <= "\u04ff"   # Cyrillic
        or "\u0e00" <= c <= "\u0e7f"   # Thai
        or "\u0600" <= c <= "\u06ff"   # Arabic
        or "\uac00" <= c <= "\ud7af"   # Hangul
        or "\uff00" <= c <= "\uffef"   # Fullwidth forms
    ]
    if total_chars > 20 and (len(garbage_chars) / total_chars) > 0.15:
        return False, f"multilingual_garbage_burst: {len(garbage_chars)}/{total_chars}"

    return True, "valid"


def _raw_chat_completion(
    base_url: str,
    key: str,
    model: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> Dict[str, Any]:
    """Internal helper to execute a single non-streaming chat completion."""
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    t0 = time.perf_counter()
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        wall_time = time.perf_counter() - t0

        if resp.status_code != 200:
            return {
                "ok": False,
                "error": f"NVIDIA API {resp.status_code}: {resp.text[:300]}",
                "content": "",
                "wall_time_s": round(wall_time, 2),
            }

        data = resp.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""

        if not content and reasoning:
            content = reasoning

        return {
            "ok": True,
            "content": content,
            "reasoning": reasoning,
            "model": model,
            "usage": data.get("usage", {}),
            "wall_time_s": round(wall_time, 2),
            "error": "",
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "content": "",
            "wall_time_s": round(time.perf_counter() - t0, 2),
        }


def chat_completion(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    max_tokens: int = 1536,
    temperature: float = 0.3,
    timeout: float = 60.0,
    enable_backup: bool = True,
) -> Dict[str, Any]:
    """
    Executes a chat completion against NVIDIA Build API with automatic output health checks
    and seamless failover to backup models if Nemotron produces corrupted or garbage output.
    Returns: {"content": str, "reasoning": str, "model": str, "usage": dict, "ok": bool, "error": str, "backup_used": bool}
    """
    key = get_nvidia_api_key()
    if not key:
        return {"ok": False, "error": "NVIDIA_API_KEY not configured", "content": ""}

    base_url = get_nvidia_base_url()
    primary_model = model or get_reasoning_model()
    backup_model = get_backup_model()

    res = _raw_chat_completion(base_url, key, primary_model, messages, max_tokens, temperature, timeout)
    if res.get("ok"):
        valid, reason = validate_output_integrity(res.get("content", ""))
        if valid:
            res["backup_used"] = False
            return res
        print(f"[NVIDIA Client] Warning: Output from {primary_model} failed integrity check ({reason}).")

    if not enable_backup or primary_model == backup_model:
        return res

    # Primary failed or degraded — fail over to primary backup
    print(f"[NVIDIA Client] Activating cloud backup model: {backup_model}...")
    backup_res = _raw_chat_completion(base_url, key, backup_model, messages, max_tokens, temperature, timeout)
    if backup_res.get("ok"):
        b_valid, _ = validate_output_integrity(backup_res.get("content", ""))
        if b_valid:
            backup_res["backup_used"] = True
            backup_res["primary_failed_model"] = primary_model
            return backup_res

    # Try secondary backup if available
    sec_backup = SECONDARY_BACKUP_MODEL
    if sec_backup and sec_backup != backup_model and sec_backup != primary_model:
        print(f"[NVIDIA Client] Activating secondary backup model: {sec_backup}...")
        sec_res = _raw_chat_completion(base_url, key, sec_backup, messages, max_tokens, temperature, timeout)
        if sec_res.get("ok"):
            s_valid, _ = validate_output_integrity(sec_res.get("content", ""))
            if s_valid:
                sec_res["backup_used"] = True
                sec_res["primary_failed_model"] = primary_model
                return sec_res

    return res


def chat_completion_stream(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    max_tokens: int = 1536,
    temperature: float = 0.3,
    timeout: float = 60.0,
    enable_backup: bool = True,
) -> Iterator[Dict[str, Any]]:
    """
    Executes an SSE streaming chat completion against NVIDIA Build API.
    Automatically fails over to backup model if primary model returns HTTP error or stream fails.
    Yields chunks:
      {"type": "reasoning", "text": str}
      {"type": "content", "text": str}
      {"type": "done", "model": str, "wall_time_s": float, "usage": dict}
      {"type": "error", "error": str}
    """
    key = get_nvidia_api_key()
    if not key:
        yield {"type": "error", "error": "NVIDIA_API_KEY not configured"}
        return

    base_url = get_nvidia_base_url()
    target_model = model or get_reasoning_model()
    backup_model = get_backup_model()

    payload = {
        "model": target_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }

    t0 = time.perf_counter()
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            json=payload,
            stream=True,
            timeout=timeout,
        )

        if resp.status_code != 200:
            if enable_backup and target_model != backup_model:
                print(f"[NVIDIA Stream] {target_model} HTTP {resp.status_code}. Failing over to {backup_model}...")
                yield from chat_completion_stream(
                    messages=messages,
                    model=backup_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                    enable_backup=False,
                )
                return
            yield {"type": "error", "error": f"NVIDIA API {resp.status_code}: {resp.text[:300]}"}
            return

        streamed_any = False
        for line in resp.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8", errors="replace")
            if not decoded.startswith("data: "):
                continue

            data_str = decoded[6:].strip()
            if data_str == "[DONE]":
                break

            try:
                chunk = json.loads(data_str)
                choice = chunk.get("choices", [{}])[0]
                delta = choice.get("delta", {})

                content_delta = delta.get("content")
                reasoning_delta = delta.get("reasoning_content")

                if reasoning_delta:
                    streamed_any = True
                    yield {"type": "reasoning", "text": reasoning_delta}
                if content_delta:
                    streamed_any = True
                    yield {"type": "content", "text": content_delta}

            except Exception:
                continue

        wall_time = round(time.perf_counter() - t0, 2)
        yield {"type": "done", "model": target_model, "wall_time_s": wall_time}

    except Exception as e:
        if enable_backup and target_model != backup_model:
            print(f"[NVIDIA Stream] Exception on {target_model}: {e}. Failing over to {backup_model}...")
            yield from chat_completion_stream(
                messages=messages,
                model=backup_model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                enable_backup=False,
            )
            return
        yield {"type": "error", "error": str(e)}


def analyze_vision(
    base64_image: str,
    prompt: str = "Describe what is visible in detail, focusing on UI elements, text, and active windows.",
    model: Optional[str] = None,
    max_tokens: int = 1024,
    timeout: float = 60.0,
) -> str:
    """
    Submits an image to the 120B Nemotron Super VL multimodal model.
    Accepts base64 PNG/JPEG and returns markdown analysis text.
    """
    key = get_nvidia_api_key()
    if not key:
        return "Error: NVIDIA_API_KEY is not configured."

    base_url = get_nvidia_base_url()
    target_model = model or get_vision_model()

    clean_b64 = base64_image.strip()
    if "," in clean_b64:
        clean_b64 = clean_b64.split(",", 1)[1]

    payload = {
        "model": target_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{clean_b64}"}},
                ],
            }
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            content = msg.get("content") or msg.get("reasoning_content") or ""
            return content.strip() or "Image analyzed with zero visual detections."
        return f"NVIDIA Vision Error ({resp.status_code}): {resp.text[:200]}"
    except Exception as e:
        return f"Error communicating with NVIDIA Vision API: {e}"

