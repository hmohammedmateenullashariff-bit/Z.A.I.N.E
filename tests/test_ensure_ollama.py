"""
tests/test_ensure_ollama.py
Unit tests verifying the Ollama neural daemon health and model detection.
"""

import unittest
from scripts.ensure_ollama import get_loaded_models, ensure_ollama


class TestEnsureOllama(unittest.TestCase):
    def test_01_get_loaded_models(self):
        models = get_loaded_models(timeout=3.0)
        self.assertIsNotNone(models, "Ollama daemon should be reachable on localhost:11434")
        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0, "Ollama must discover at least one model in D:\\ollama\\models")

    def test_02_ensure_ollama_online(self):
        result = ensure_ollama(timeout_seconds=5)
        self.assertTrue(result, "ensure_ollama must report ready and healthy")


if __name__ == "__main__":
    unittest.main()

