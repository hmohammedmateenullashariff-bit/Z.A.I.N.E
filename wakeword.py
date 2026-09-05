"""
Z.A.I.N.E Agent — Wake Word Detection (Zero-Disk & Low Latency)
Continuously listens in short chunks in RAM for "zaine" (with phonetic tolerance).
Plays an audio earcon chime immediately upon positive detection.
"""

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from voice import play_chime

SAMPLE_RATE = 16000
CHUNK_SECONDS = 2

# "tiny" runs in-memory on CPU without hogging resources.
_wake_model = WhisperModel("tiny", device="cpu", compute_type="int8")

# Common ways Whisper mis-hears "Zaine" — checked both exactly and fuzzily.
WAKE_VARIANTS = [
    "zaine", "zain", "zayn", "zane", "zayne", "zin", "zinn", "zen",
    "xin", "sain", "sayin", "zaeen", "zaeene", "zayeen", "zyne",
    "zein", "xein", "zhen", "jain", "jayne", "zaian", "zayan",
    "xayn", "zayin", "zaen",
]


def _record_chunk(seconds: int = CHUNK_SECONDS) -> np.ndarray:
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    return audio


def _levenshtein(a: str, b: str) -> int:
    """Simple edit distance, no external dependency needed."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                prev[j] + 1,       # deletion
                curr[j - 1] + 1,   # insertion
                prev[j - 1] + (ca != cb),  # substitution
            )
        prev = curr
    return prev[-1]


def _heard_wake_word(audio: np.ndarray, wake_word: str) -> bool:
    if audio is None or len(audio) == 0:
        return False

    # In-memory float32 normalization
    audio_f32 = audio.flatten().astype(np.float32) / 32768.0

    # Quick energy gate: if complete silence, skip running the whisper model
    rms = np.sqrt(np.mean(audio_f32 ** 2))
    if rms < 0.008:
        return False

    try:
        segments, _ = _wake_model.transcribe(audio_f32, language="en")
        text = " ".join(seg.text for seg in segments).lower()
    except Exception:
        return False

    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    words = cleaned.split()
    target = wake_word.lower()
    variants = WAKE_VARIANTS if target == "zaine" else [target]

    for word in words:
        for variant in variants:
            max_dist = 1 if len(variant) <= 4 else 2
            if _levenshtein(word, variant) <= max_dist:
                return True
        if _levenshtein(word, target) <= (2 if len(target) > 3 else 1):
            return True
    return False


def wait_for_wake_word(wake_word: str = "zaine"):
    """Blocks until the wake word is heard, plays audio chime, then returns."""
    while True:
        audio = _record_chunk()
        if _heard_wake_word(audio, wake_word):
            try:
                play_chime()
            except Exception:
                pass
            return

