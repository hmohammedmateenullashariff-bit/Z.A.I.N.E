"""
tests/test_nvidia_integration.py
Tests NVIDIA Build cloud escalation for dual-tier models:
- nvidia/nemotron-3-ultra-550b-a55b (Deep Reasoning & Complex Code)
- nvidia/nemotron-3.5-super-vl-120b-a12b (Multimodal Vision-Language)
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

load_dotenv()

import nvidia_client
from core_router import router
from tools import consult_nemotron_brain_tool
import vision


def test_nvidia_client_config():
    """Verifies that nvidia_client correctly reads .env settings."""
    assert nvidia_client.is_nvidia_available() is True
    assert "nemotron-3-ultra-550b" in nvidia_client.get_reasoning_model()
    assert "nemotron-3.5-super-vl-120b" in nvidia_client.get_vision_model()


def test_router_escalation_classification():
    """Verifies that the router escalates complex tasks to Nemotron and leaves reflex tasks local."""
    # 1. Reflex tasks stay local
    reflex_target = router.get_escalation_target("REFLEX", prompt="hello what time is it")
    assert reflex_target is None

    # 2. Deep code tasks escalate to 550B Nemotron
    code_target = router.get_escalation_target("DEEP_CODE", prompt="architect a distributed transactional cache")
    assert code_target is not None
    assert code_target["provider"] == "nvidia"
    assert "nemotron-3-ultra-550b" in code_target["model"]

    # 3. Deep reasoning tasks escalate to 550B Nemotron
    reasoning_target = router.get_escalation_target("DEEP_REASONING", prompt="analyze system trade-offs in detail")
    assert reasoning_target is not None
    assert reasoning_target["provider"] == "nvidia"
    assert "nemotron-3-ultra-550b" in reasoning_target["model"]

    # 4. Vision tasks escalate to 120B Super VL
    vision_target = router.get_escalation_target("VISION", prompt="look at my screen")
    assert vision_target is not None
    assert vision_target["provider"] == "nvidia"
    assert "nemotron-3.5-super-vl-120b" in vision_target["model"]

    # 5. Privacy boundary: private session NEVER routes to cloud
    blocked_target = router.get_escalation_target("DEEP_CODE", prompt="architect this", session_private=True)
    assert blocked_target is None


def test_consult_nemotron_brain_tool_mocked():
    """Verifies consult_nemotron_brain_tool executes cleanly and formats output."""
    with patch("nvidia_client.chat_completion") as mock_comp:
        mock_comp.return_value = {
            "ok": True,
            "content": "Architecture Analysis: Use Raft consensus with WAL.",
            "reasoning": "Raft is optimal for consistency.",
            "model": "nvidia/nemotron-3-ultra-550b-a55b",
        }
        res = consult_nemotron_brain_tool("Design a fault-tolerant KV store")
        assert "NVIDIA Nemotron" in res
        assert "Use Raft consensus" in res


def test_vision_escalation_fallback():
    """Verifies vision fallback to local Moondream when cloud fails."""
    tiny_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    with patch("nvidia_client.analyze_vision", side_effect=Exception("API offline")):
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"response": "Local Moondream Red Pixel"}
            mock_post.return_value = mock_resp

            res = vision.analyze_image_with_ollama(tiny_b64, prompt="What is this?")
            assert "Local Moondream Red Pixel" in res


def test_output_integrity_validator():
    """Verifies that validate_output_integrity catches loops and garbage character bursts."""
    # 1. Clean response passes
    ok, reason = nvidia_client.validate_output_integrity(
        "Here is the architecture breakdown for your real-time distributed telemetry pipeline using Kafka and ClickHouse."
    )
    assert ok is True
    assert reason == "valid"

    # 2. Phrase repetition loop fails
    looping_text = "the data pipeline the data pipeline the data pipeline the data pipeline the data pipeline the data pipeline"
    ok, reason = nvidia_client.validate_output_integrity(looping_text)
    assert ok is False
    assert "repetition_loop" in reason

    # 3. Single character repeat fails
    char_repeat = "System processing failure xxxxxxxxxxxxxxxxxxxxxxxx"
    ok, reason = nvidia_client.validate_output_integrity(char_repeat)
    assert ok is False
    assert "character_repetition_loop" in reason

    # 4. Multilingual token collapse fails
    corrupted = "System is starting \u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341 \u043f\u0440\u0438\u0432\u0435\u0442 \u043a\u0430\u043a \u0434\u0435\u043b\u0430 \u4e00\u4e8c\u4e09\u56db\u4e94"
    ok, reason = nvidia_client.validate_output_integrity(corrupted)
    assert ok is False
    assert "multilingual_garbage_burst" in reason


def test_automatic_backup_failover_on_garbage():
    """Verifies that chat_completion automatically falls over to backup model when primary outputs garbage."""
    # Mock _raw_chat_completion: first call (primary) returns corrupted text, second call (backup) returns clean text
    with patch("nvidia_client._raw_chat_completion") as mock_raw:
        mock_raw.side_effect = [
            # Call 1: primary model returns phrase repetition loop
            {
                "ok": True,
                "content": "bad output bad output bad output bad output bad output bad output bad output",
                "reasoning": "",
                "model": "nvidia/nemotron-3-ultra-550b-a55b",
                "usage": {},
                "wall_time_s": 0.5,
                "error": "",
            },
            # Call 2: backup model returns pristine valid output
            {
                "ok": True,
                "content": "Here is the resilient architecture you requested.",
                "reasoning": "",
                "model": "minimaxai/minimax-m3.1-flash",
                "usage": {},
                "wall_time_s": 0.3,
                "error": "",
            },
        ]

        res = nvidia_client.chat_completion(
            messages=[{"role": "user", "content": "Design pipeline"}],
            model="nvidia/nemotron-3-ultra-550b-a55b",
            enable_backup=True,
        )

        assert res["ok"] is True
        assert res.get("backup_used") is True
        assert res["model"] == "minimaxai/minimax-m3.1-flash"
        assert "resilient architecture" in res["content"]


