"""
Z.A.I.N.E Agent — Voice Layer (High Performance & Low Latency)
- In-memory Speech-to-Text: faster-whisper without temporary disk writes
- Dynamic VAD: stops recording automatically when speech pauses
- Audio Chime: instant harmonic earcon when wake word triggers
- Sentence TTS: streaming neural speech synthesis via Piper
"""

import os
import re
import subprocess
import sys
import time
import threading
try:
    import msvcrt
except ImportError:
    msvcrt = None
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from piper import PiperVoice
from piper.config import SynthesisConfig

SAMPLE_RATE = 16000
RECORD_SECONDS = 7

# Load once, reused across calls. "base" is a good speed/accuracy balance on CPU.
_whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

# --- TTS setup (Hybrid: Edge-TTS Ultra-Realistic Neural Voice + Piper Offline Fallback) ---
# Edge-TTS options: 'en-GB-RyanNeural' (Jarvis British), 'en-US-ChristopherNeural' (Ultron Dark Baritone)
EDGE_VOICE = os.getenv("TTS_VOICE", "en-GB-RyanNeural")
EDGE_PITCH = os.getenv("TTS_PITCH", "+0Hz")
EDGE_RATE = os.getenv("TTS_RATE", "+0%")
USE_EDGE_TTS = os.getenv("USE_EDGE_TTS", "true").lower() in ("true", "1", "yes")

try:
    import edge_tts
    import av
    import asyncio
    import io
    import wave
except ImportError:
    edge_tts = None
    av = None
    io = None
    wave = None

try:
    import winsound
except ImportError:
    winsound = None

# Piper fallback
VOICE_NAME = "en_GB-alan-medium"
VOICES_DIR = os.path.join(os.path.dirname(__file__), "voices")
MODEL_PATH = os.path.join(VOICES_DIR, f"{VOICE_NAME}.onnx")
CONFIG_PATH = os.path.join(VOICES_DIR, f"{VOICE_NAME}.onnx.json")


def _ensure_voice_downloaded():
    if os.path.exists(MODEL_PATH) and os.path.exists(CONFIG_PATH):
        return
    os.makedirs(VOICES_DIR, exist_ok=True)
    print(f"Downloading voice '{VOICE_NAME}' (one-time, ~60MB)...")
    subprocess.run(
        [sys.executable, "-m", "piper.download_voices", VOICE_NAME, "--download-dir", VOICES_DIR],
        check=True,
    )


_ensure_voice_downloaded()
_piper_voice = PiperVoice.load(MODEL_PATH, config_path=CONFIG_PATH)


def set_voice(voice_name: str) -> str:
    """Dynamically changes Zaine's active speech voice."""
    global EDGE_VOICE
    EDGE_VOICE = voice_name.strip()
    return f"Voice successfully switched to '{EDGE_VOICE}'."


def _synthesize_edge_tts(clean_text: str, voice: str = None, pitch: str = None, rate: str = None):
    """
    Synthesizes speech using Edge-TTS and decodes MP3 stream in RAM via PyAV.
    Returns (numpy_int16_array, sample_rate) or (None, 0).
    """
    if edge_tts is None or av is None:
        return None, 0

    target_voice = voice or EDGE_VOICE
    target_pitch = pitch or EDGE_PITCH
    target_rate = rate or EDGE_RATE

    async def _async_gen():
        comm = edge_tts.Communicate(clean_text, target_voice, pitch=target_pitch, rate=target_rate)
        mp3_data = b""
        async for chunk in comm.stream():
            if _interrupt_event.is_set():
                return None
            if chunk["type"] == "audio":
                mp3_data += chunk["data"]
        return mp3_data

    try:
        mp3_data = asyncio.run(_async_gen())
        if not mp3_data or _interrupt_event.is_set():
            return None, 0

        container = av.open(io.BytesIO(mp3_data))
        audio_stream = container.streams.audio[0]
        sample_rate = audio_stream.rate
        frames = []
        for frame in container.decode(audio=0):
            if _interrupt_event.is_set():
                return None, 0
            frames.append(frame.to_ndarray())

        if not frames:
            return None, 0

        audio = np.concatenate(frames, axis=1) if len(frames[0].shape) > 1 else np.concatenate(frames)
        if audio.ndim > 1:
            audio = audio[0]

        # Convert float32 [-1.0, 1.0] from PyAV to int16 PCM (vital: scale by 32767 to avoid zeroing out audio)
        if audio.dtype in (np.float32, np.float64):
            audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        else:
            audio_int16 = audio.astype(np.int16)

        return audio_int16, sample_rate
    except Exception as e:
        print(f"[Edge-TTS fallback to Piper notice]: {e}")
        return None, 0


def play_chime():
    """Plays a crisp, high-tech two-tone chime via sounddevice with winsound fallback."""
    sr = 44100
    t1 = np.linspace(0, 0.07, int(sr * 0.07), endpoint=False)
    tone1 = 0.22 * np.sin(2 * np.pi * 587 * t1) * np.linspace(1, 0.3, len(t1))
    t2 = np.linspace(0, 0.14, int(sr * 0.14), endpoint=False)
    tone2 = 0.28 * np.sin(2 * np.pi * 880 * t2) * np.exp(-12 * t2)
    chime = np.concatenate([tone1, tone2]).astype(np.float32)
    try:
        sd.play(chime, samplerate=sr)
    except Exception:
        chime_int16 = (np.clip(chime, -1.0, 1.0) * 32767).astype(np.int16)
        _play_winsound_bytes(chime_int16, sr)


def play_ultron_chime():
    """Plays a menacing, cybernetic seismic bass-drop earcon for Ultron Protocol activation."""
    sr = 44100
    duration = 1.1
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Deep cybernetic sub-bass drop: 240Hz exponentially dropping down to 48Hz infrasound rumble
    f_drop = 240 * np.exp(-3.8 * t) + 48
    phase = 2 * np.pi * np.cumsum(f_drop) / sr
    sub_bass = 0.55 * np.sin(phase)
    # Heavy metallic distortion overtone (320Hz modulated by 18Hz pulse)
    metallic = 0.22 * np.sin(2 * np.pi * 320 * t + 0.3 * np.sin(2 * np.pi * 18 * t)) * np.exp(-4.5 * t)
    # Sinister mechanical buzz
    buzz = 0.12 * np.sin(2 * np.pi * 96 * t) * np.exp(-2.5 * t)
    envelope = np.minimum(t / 0.04, 1.0) * (1.0 - (t / duration) ** 1.5)
    chime = ((sub_bass + metallic + buzz) * envelope).astype(np.float32)
    try:
        sd.play(chime, samplerate=sr)
    except Exception:
        chime_int16 = (np.clip(chime, -1.0, 1.0) * 32767).astype(np.int16)
        _play_winsound_bytes(chime_int16, sr)


def set_ultron_mode(enable: bool = True) -> str:
    """Switches Zaine between classic Jarvis voice and deep commanding Ultron baritone."""
    global EDGE_VOICE, EDGE_PITCH, EDGE_RATE
    if enable:
        EDGE_VOICE = os.getenv("ULTRON_VOICE", "en-US-ChristopherNeural")
        EDGE_PITCH = "-24Hz"
        EDGE_RATE = "-6%"
        return f"Ultron dark neural baritone engaged ({EDGE_VOICE} at {EDGE_PITCH}, {EDGE_RATE})."
    else:
        EDGE_VOICE = os.getenv("TTS_VOICE", "en-GB-RyanNeural")
        EDGE_PITCH = "+0Hz"
        EDGE_RATE = "+0%"
        return f"Jarvis neural voice restored ({EDGE_VOICE})."


def record_audio(duration: int = RECORD_SECONDS, use_vad: bool = True) -> np.ndarray:
    """Records from the microphone. If use_vad is True, cuts off after natural silence."""
    if not use_vad:
        print(f"[Listening for {duration}s...]")
        audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        sd.wait()
        return audio

    print("[Listening...]")
    block_duration = 0.08  # 80ms chunks
    block_samples = int(SAMPLE_RATE * block_duration)
    max_blocks = int(duration / block_duration)
    silence_threshold_blocks = int(0.9 / block_duration)  # ~900ms silence to cut off

    collected_blocks = []
    speech_detected = False
    silence_count = 0
    speech_blocks = 0

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=block_samples) as stream:
            ambient_rms = 300.0
            for i in range(max_blocks):
                block, _ = stream.read(block_samples)
                rms = float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))
                collected_blocks.append(block)

                if i < 2:
                    ambient_rms = max(ambient_rms, rms)
                    continue

                threshold = max(450.0, ambient_rms * 2.0)

                if rms > threshold:
                    speech_detected = True
                    speech_blocks += 1
                    silence_count = 0
                else:
                    if speech_detected:
                        silence_count += 1
                        if silence_count >= silence_threshold_blocks and speech_blocks >= 4:
                            break
    except Exception:
        # Fallback to fixed recording if InputStream encounters device issues
        audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        sd.wait()
        return audio

    if collected_blocks:
        return np.concatenate(collected_blocks)
    return np.zeros((0, 1), dtype="int16")


def transcribe(audio: np.ndarray) -> str:
    """Transcribes audio directly in RAM with faster-whisper (zero disk writes)."""
    if audio is None or len(audio) == 0:
        return ""

    if audio.dtype == np.int16:
        audio_f32 = audio.flatten().astype(np.float32) / 32768.0
    else:
        audio_f32 = audio.flatten().astype(np.float32)

    segments, _ = _whisper_model.transcribe(audio_f32, language=None)
    return " ".join(seg.text.strip() for seg in segments).strip()


def listen(duration: int = RECORD_SECONDS) -> str:
    """Full pipeline: record from mic (with dynamic silence cutoff), return transcribed text."""
    audio = record_audio(duration, use_vad=True)
    return transcribe(audio)


# Default synthesis config for energetic, punchy delivery
_syn_config = SynthesisConfig(length_scale=0.92)


def _clean_for_speech(text: str) -> str:
    """Cleans markdown formatting, links, raw URLs, and special symbols for natural TTS pronunciation."""
    import re
    # 1. Normalize Z.A.I.N.E / Z.A.I.N.E. / Z-A-I-N-E to "Zaine" so TTS pronounces it as a fluid name
    text = re.sub(r'\bZ[.\-_ ]?A[.\-_ ]?I[.\-_ ]?N[.\-_ ]?E\.?\b', 'Zaine', text, flags=re.IGNORECASE)
    # 2. Convert markdown links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 3. Remove standalone raw URLs so TTS doesn't spell them out
    text = re.sub(r'https?://\S+', '', text)
    # 4. Remove markdown markers (*, _, `, #)
    text = re.sub(r'[\*_`#]', '', text)
    # 5. Remove emojis and unpronounceable symbols, keep letters, numbers, and basic punctuation
    text = re.sub(r'[^\w\s.,!?\'"\-]', '', text)
    return " ".join(text.split())



_interrupt_event = threading.Event()
_is_speaking_now = False

BARGE_IN_KEYWORDS = {
    "stop", "zaine", "wait", "hold", "ruko", "chup", "quiet",
    "cancel", "shh", "listen", "enough", "pause", "shut", "exit"
}


def stop_speaking():
    """Immediately stops active neural voice playback with zero latency."""
    global _is_speaking_now
    _is_speaking_now = False
    _interrupt_event.set()
    try:
        sd.stop()
    except Exception:
        pass


def is_speaking() -> bool:
    """Returns True if Zaine is currently speaking out loud."""
    return _is_speaking_now


def _resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Fast in-RAM linear interpolation resampling for zero-dependency audio rate adaptation."""
    if orig_sr == target_sr:
        return audio
    num_samples = int(round(len(audio) * float(target_sr) / orig_sr))
    indices = np.linspace(0, len(audio) - 1, num_samples)
    return np.interp(indices, np.arange(len(audio)), audio).astype(audio.dtype)


def _play_winsound_bytes(audio_int16: np.ndarray, sr: int, stop_event: threading.Event = None) -> bool:
    """Fallback playback using Windows OS core multimedia audio subsystem."""
    if winsound is None:
        return False
    try:
        bio = io.BytesIO()
        with wave.open(bio, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(audio_int16.tobytes())
        wav_bytes = bio.getvalue()

        done_event = threading.Event()
        def _runner():
            try:
                winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
            except Exception:
                pass
            finally:
                done_event.set()

        t = threading.Thread(target=_runner, daemon=True)
        t.start()

        duration = len(audio_int16) / sr
        start = time.time()
        while not done_event.is_set() and (time.time() - start < duration + 0.5):
            if stop_event and stop_event.is_set():
                try:
                    winsound.PlaySound(None, winsound.SND_PURGE)
                except Exception:
                    pass
                return False
            time.sleep(0.02)
        return True
    except Exception as e:
        print(f"[Winsound playback notice]: {e}")
        return False


def _barge_in_monitor_thread(stop_event: threading.Event):
    """
    Monitors microphone audio and keyboard hits while Zaine is speaking.
    If the user presses ESC/Space/q or speaks an interruption keyword, it halts TTS immediately.
    """
    block_duration = 0.12  # 120ms slices
    block_samples = int(SAMPLE_RATE * block_duration)
    speech_buffer = []

    # Drain any lingering keyboard input buffer before starting monitor
    if msvcrt:
        try:
            while msvcrt.kbhit():
                msvcrt.getch()
        except Exception:
            pass

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=block_samples) as stream:
            while not stop_event.is_set():
                # 1. Explicit console keypress barge-in (ESC, Space, 'q')
                if msvcrt and msvcrt.kbhit():
                    try:
                        ch = msvcrt.getch()
                        if ch in (b'\x1b', b' ', b'q', b'Q'):
                            print("\n[Barge-In: Keypress (ESC/Space) -> Halting speech]")
                            stop_speaking()
                            break
                    except Exception:
                        pass

                # 2. Mic audio energy & keyword inspection
                try:
                    block, _ = stream.read(block_samples)
                except Exception:
                    time.sleep(0.04)
                    continue

                rms = float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))
                # Energy threshold for intentional user speech above ambient
                if rms > 750.0:
                    speech_buffer.append(block)
                    if len(speech_buffer) >= 3:  # ~360ms of speech collected
                        combined = np.concatenate(speech_buffer)
                        audio_f32 = combined.flatten().astype(np.float32) / 32768.0
                        try:
                            segments, _ = _whisper_model.transcribe(audio_f32, language="en")
                            detected = " ".join(s.text.lower() for s in segments)
                            cleaned = re.sub(r"[^\w\s]", " ", detected).split()
                            if any(w in BARGE_IN_KEYWORDS for w in cleaned):
                                print(f"\n[Barge-In: Spoken keyword detected ('{detected.strip()}') -> Halting speech]")
                                stop_speaking()
                                break
                        except Exception:
                            pass
                        speech_buffer = speech_buffer[-1:]
                else:
                    if speech_buffer:
                        speech_buffer = []

                time.sleep(0.01)
    except Exception:
        # Fallback to keypress monitoring if microphone InputStream cannot be shared
        while not stop_event.is_set():
            if msvcrt and msvcrt.kbhit():
                try:
                    ch = msvcrt.getch()
                    if ch in (b'\x1b', b' ', b'q', b'Q'):
                        print("\n[Barge-In: Keypress (ESC/Space) -> Halting speech]")
                        stop_speaking()
                        break
                except Exception:
                    pass
            time.sleep(0.05)


def speak_sentence(text: str, allow_barge_in: bool = True) -> bool:
    """
    Synthesizes and speaks a single sentence immediately.
    Returns True if completed normally, False if interrupted by user barge-in.
    """
    global _is_speaking_now
    clean = _clean_for_speech(text)
    if not clean:
        return True

    _interrupt_event.clear()
    monitor_stop = threading.Event()
    monitor_thread = None

    if allow_barge_in:
        monitor_thread = threading.Thread(
            target=_barge_in_monitor_thread,
            args=(monitor_stop,),
            daemon=True,
        )
        monitor_thread.start()

    try:
        audio = None
        sr = 0

        # 1. Try High-Fidelity Edge-TTS first (if online & enabled)
        if USE_EDGE_TTS and edge_tts and av:
            audio, sr = _synthesize_edge_tts(clean)

        # 2. Offline Fallback to Local Piper Voice
        if audio is None or len(audio) == 0:
            if _interrupt_event.is_set():
                _is_speaking_now = False
                monitor_stop.set()
                return False

            chunks = []
            for chunk in _piper_voice.synthesize(clean, syn_config=_syn_config):
                if _interrupt_event.is_set():
                    _is_speaking_now = False
                    monitor_stop.set()
                    return False
                chunks.append(chunk)

            if not chunks:
                monitor_stop.set()
                return True

            sr = chunks[0].sample_rate
            audio = np.concatenate([c.audio_int16_array for c in chunks])

        if _interrupt_event.is_set():
            _is_speaking_now = False
            monitor_stop.set()
            return False

        _is_speaking_now = True

        # Query native output rate to avoid PortAudio sample rate errors
        native_sr = sr
        try:
            out_info = sd.query_devices(kind='output')
            if out_info and 'default_samplerate' in out_info:
                native_sr = int(out_info['default_samplerate'])
        except Exception:
            native_sr = sr

        playback_audio = audio
        playback_sr = sr
        if native_sr > 0 and native_sr != sr:
            playback_audio = _resample_audio(audio, sr, native_sr)
            playback_sr = native_sr

        played_ok = False
        try:
            sd.play(playback_audio, samplerate=playback_sr)
            duration = len(playback_audio) / playback_sr
            start_time = time.time()

            # Non-blocking slice checking allows sub-30ms instant barge-in cut-off
            while time.time() - start_time < duration:
                if _interrupt_event.is_set():
                    sd.stop()
                    _is_speaking_now = False
                    monitor_stop.set()
                    return False
                time.sleep(0.02)

            sd.wait()
            played_ok = True
        except Exception as sd_err:
            print(f"[SoundDevice notice: {sd_err} -> Routing through Windows multimedia audio engine]")
            played_ok = _play_winsound_bytes(audio, sr, stop_event=_interrupt_event)

        _is_speaking_now = False
        monitor_stop.set()
        return played_ok
    except Exception as e:
        print(f"(Voice playback error: {e})")
        _is_speaking_now = False
        monitor_stop.set()
        return True
    finally:
        monitor_stop.set()


def speak(text: str, allow_barge_in: bool = True) -> bool:
    """Speaks the given text out loud using the active neural voice."""
    return speak_sentence(text, allow_barge_in=allow_barge_in)

