"""
Z.A.I.N.E — Phase 8: Paul Bettany Jarvis Voice Persona Cloner & Acoustic Engine
Emulates the iconic Paul Bettany J.A.R.V.I.S vocal cadence:
- Salutation: Strictly "Sir" (or "Ma'am" if female persona detected)
- British elegance: Courteous, unflappable, concise, intellectual
- Automatic Acronym De-spelling: Transcribes "Z.A.I.N.E" -> "Zaine" (/zeɪn/)
- Fine-tuned SSML parameters: Pitch -2Hz, Rate +4%, Volume +0%
"""

import os
import re
import sys
import asyncio
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent

# Preferred Jarvis acoustic voices
JARVIS_VOICE_MALE = "en-GB-RyanNeural"     # Refined British timbre
JARVIS_VOICE_ALT = "en-GB-ThomasNeural"   # Alternative crisp British voice
JARVIS_VOICE_FEMALE = "en-GB-SoniaNeural" # Crisp British female counterpart

DEFAULT_RATE = "+4%"
DEFAULT_PITCH = "-2Hz"
DEFAULT_VOLUME = "+0%"

# Elegant Jarvis contextual prefixes
TASK_AFFIRMATIONS = [
    "Right away, {salutation}.",
    "At once, {salutation}.",
    "Initiating execution now, {salutation}.",
    "Of course, {salutation}.",
    "Processing your request, {salutation}.",
    "Straightaway, {salutation}."
]

COMPLETION_AFFIRMATIONS = [
    "All parameters are nominal, {salutation}.",
    "Execution concluded successfully, {salutation}.",
    "Task completed to specification, {salutation}."
]


def clean_text_for_speech(text: str, salutation: str = "Sir") -> str:
    """
    Sanitizes raw LLM output for natural Paul Bettany speech:
    1. Replaces 'Z.A.I.N.E' / 'Z.A.I.N.E.' with 'Zaine' (pronounced /zeɪn/)
    2. Strips Markdown code fences, backticks, asterisks, hash headers
    3. Normalizes slang to proper respectful address
    4. Strips URLs or replaces them with 'the website link'
    """
    if not text:
        return ""

    # Replace acronym spellouts so TTS never says "Zee Ay Eye Enn Ee"
    text = re.sub(r'Z\.A\.I\.N\.E\.?', 'Zaine', text, flags=re.IGNORECASE)
    text = re.sub(r'\bZ-A-I-N-E\b', 'Zaine', text, flags=re.IGNORECASE)
    text = re.sub(r'\bZ\s+A\s+I\s+N\s+E\b', 'Zaine', text, flags=re.IGNORECASE)

    # Enforce respectful salutation
    slang_patterns = [r'\bMateen bhai\b', r'\bbhai\b', r'\bdude\b', r'\bbro\b', r'\bbuddy\b', r'\bman\b']
    for pattern in slang_patterns:
        text = re.sub(pattern, salutation, text, flags=re.IGNORECASE)

    # Strip code fences and inline backticks
    text = re.sub(r'```[\s\S]*?```', ' [Code block omitted for brevity] ', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Strip markdown headers, bold, italics
    text = re.sub(r'#+\s*', '', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)

    # Strip bullet points
    text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)

    # Strip raw URLs
    text = re.sub(r'https?://\S+', 'link', text)

    # Condense multiple whitespace/newlines
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def build_jarvis_ssml(text: str, voice: str = JARVIS_VOICE_MALE, rate: str = DEFAULT_RATE, pitch: str = DEFAULT_PITCH) -> str:
    """Builds standard SSML payload for Edge-TTS with refined cadence."""
    cleaned = clean_text_for_speech(text)
    # Escape XML entities
    escaped = cleaned.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    ssml = f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-GB'>
    <voice name='{voice}'>
        <prosody rate='{rate}' pitch='{pitch}' volume='{DEFAULT_VOLUME}'>
            {escaped}
        </prosody>
    </voice>
</speak>"""
    return ssml


async def synthesize_to_file(text: str, output_path: str, voice: str = JARVIS_VOICE_MALE, rate: str = DEFAULT_RATE, pitch: str = DEFAULT_PITCH) -> bool:
    """Synthesizes speech to an MP3 file using edge-tts with Jarvis acoustic profile."""
    try:
        import edge_tts
        cleaned = clean_text_for_speech(text)
        if not cleaned:
            return False

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        communicate = edge_tts.Communicate(
            text=cleaned,
            voice=voice,
            rate=rate,
            pitch=pitch
        )
        await communicate.save(output_path)
        return True
    except Exception as e:
        print(f"[JarvisVoice] Edge-TTS error: {e}", file=sys.stderr)
        return False


def play_audio_file(file_path: str):
    """Plays an audio file cleanly on Windows using pygame or playsound."""
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except Exception:
        # Fallback to powershell media player
        os.system(f'powershell -c "(New-Object Media.SoundPlayer \'{file_path}\').PlaySync();"')


def jarvis_speak(text: str, salutation: str = "Sir", play_now: bool = False, output_file: Optional[str] = None) -> Optional[str]:
    """
    Public synchronous facade for Paul Bettany voice synthesis.
    Returns path to synthesized audio file.
    """
    if not output_file:
        cache_dir = PROJECT_ROOT / "data" / "voice_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        output_file = str(cache_dir / f"jarvis_{abs(hash(text)) % 1000000}.mp3")

    cleaned = clean_text_for_speech(text, salutation=salutation)
    try:
        asyncio.run(synthesize_to_file(cleaned, output_file, voice=JARVIS_VOICE_MALE))
        if play_now and Path(output_file).exists():
            play_audio_file(output_file)
        return output_file
    except Exception as e:
        print(f"[JarvisVoice] Speech synthesis failed: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    print("Testing Paul Bettany Jarvis Voice Persona Engine...")
    test_phrase = "Good evening, Sir. Z.A.I.N.E is operating at peak computational efficiency. All neural sub-agents stand ready."
    print("Original: ", test_phrase)
    cleaned = clean_text_for_speech(test_phrase)
    print("Cleaned:  ", cleaned)
    assert "Zaine" in cleaned, "Acronym normalization failed!"
    assert "Z.A.I.N.E" not in cleaned, "Acronym was not replaced!"
    print("Acronym de-spelling test passed!")

    cache_path = str(PROJECT_ROOT / "data" / "voice_cache" / "test_jarvis.mp3")
    res = jarvis_speak(test_phrase, output_file=cache_path)
    if res and Path(res).exists():
        print(f"Audio synthesized successfully: {res} ({Path(res).stat().st_size} bytes)")
    else:
        print("Synthesis skipped or offline.")
