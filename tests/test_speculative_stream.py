"""
tests/test_speculative_stream.py
Unit tests for the Speculative Dual-Stream Voice Synthesizer.
"""

import unittest
from core.voice_stream import SpeculativeVoiceEngine


class TestSpeculativeVoice(unittest.TestCase):
    def setUp(self):
        self.engine = SpeculativeVoiceEngine()

    def test_01_sentence_synthesis_or_fallback(self):
        # Even without Piper installed or in mock mode, synthesize_sentence shouldn't throw
        res = self.engine.synthesize_sentence("System online. Diagnostics nominal.")
        if res is not None:
            audio, sr = res
            self.assertEqual(sr, 22050)
            self.assertGreater(len(audio), 0)

    def test_02_barge_in_interruption(self):
        self.engine.interrupted = False
        self.engine.trigger_barge_in()
        self.assertTrue(self.engine.interrupted)

    def test_03_empty_sentence_handling(self):
        self.assertIsNone(self.engine.synthesize_sentence(""))
        self.assertIsNone(self.engine.synthesize_sentence("   "))


if __name__ == "__main__":
    unittest.main()
