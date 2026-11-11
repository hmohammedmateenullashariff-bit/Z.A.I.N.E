"""
Z.A.I.N.E — Microphone Diagnostic
Run this directly: python test_mic.py
It records 3 seconds, tells you the audio volume level (to confirm the mic
is actually capturing sound), and prints exactly what Whisper heard.
"""

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as write_wav
from faster_whisper import WhisperModel
import tempfile
import os

SAMPLE_RATE = 16000
DURATION = 3

print("Available input devices:")
print(sd.query_devices())
print()
print(f"Using default input device: {sd.default.device}")
print()

input("Press Enter, then speak clearly for 3 seconds...")
print("🎙️ Recording...")

audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
sd.wait()
print("🎙️ Done recording.")

volume = np.abs(audio).mean()
peak = np.abs(audio).max()
print(f"\nAverage volume: {volume:.1f}  |  Peak volume: {peak}")
if peak < 200:
    print("⚠️  Very low/no signal detected — mic may not be capturing audio at all.")
    print("    Check Windows sound settings > Input > make sure the right mic is selected")
    print("    and the input volume slider isn't muted/near zero.")
else:
    print("✅ Mic is picking up sound.")

with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
    write_wav(tmp.name, SAMPLE_RATE, audio)
    tmp_path = tmp.name

print("\nTranscribing with Whisper (tiny model)...")
model = WhisperModel("tiny", device="cpu", compute_type="int8")
segments, _ = model.transcribe(tmp_path, language="en")
text = " ".join(seg.text for seg in segments).strip()
os.remove(tmp_path)

print(f"\nWhisper heard: \"{text}\"")
if not text:
    print("⚠️  Whisper transcribed nothing — either no sound, or too quiet/unclear.")
