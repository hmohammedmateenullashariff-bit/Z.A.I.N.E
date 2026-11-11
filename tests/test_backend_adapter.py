"""
tests/test_backend_adapter.py
Unit tests verifying the pluggable inference backend abstraction.
"""

import unittest
from core.backend_adapter import OllamaBackend, LlamaCppServerBackend, get_inference_backend


class TestBackendAdapter(unittest.TestCase):
    def test_01_ollama_backend_alive(self):
        backend = OllamaBackend()
        self.assertTrue(backend.is_alive(), "Ollama daemon must report alive on localhost:11434")
        models = backend.list_models()
        self.assertGreater(len(models), 0, "Ollama backend must list available models")

    def test_02_default_backend_resolution(self):
        backend = get_inference_backend()
        self.assertIsInstance(backend, OllamaBackend)

    def test_03_llamacpp_backend_instantiation(self):
        backend = LlamaCppServerBackend("http://127.0.0.1:8080")
        self.assertEqual(backend.base_url, "http://127.0.0.1:8080")


if __name__ == "__main__":
    unittest.main()

