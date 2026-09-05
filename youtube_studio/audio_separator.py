"""
Z.A.I.N.E — AI Audio Stem Separation Engine (Powered by Meta Demucs)
Splits anime combat audio and music into isolated stems:
- Vocals (Character dialogue, battle shouts, breath, grunts)
- Drums (Kick drum, percussion, snap, snare)
- Bass (Sub-bass, 808s, low-end drops)
- Other (Original soundtrack, instruments, synthesizer)

Use cases:
1. Isolate raw Japanese voice lines and battle screams to overlay on custom battle OSTs.
2. Isolate drum & bass transients for 100% precise beat-drop video cuts.
3. Clean vocal removal to create custom instrumentals.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STEMS_DIR = PROJECT_ROOT / "workspace" / "audio" / "stems"
STEMS_DIR.mkdir(parents=True, exist_ok=True)


def get_ffmpeg_binary() -> str:
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def extract_audio_from_video(video_path: str, output_wav_path: str) -> str:
    """Extracts high-fidelity 44.1kHz stereo WAV from any video file."""
    ffmpeg = get_ffmpeg_binary()
    cmd = [
        ffmpeg,
        "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        output_wav_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_wav_path


def separate_audio_stems(
    audio_or_video_path: str,
    model_name: str = "htdemucs",
    output_dir: Optional[str] = None,
) -> Dict[str, str]:
    """
    Runs Meta Demucs deep neural stem separation on the audio track.
    Returns dictionary with paths to:
    {
        "vocals": ".../vocals.wav",
        "drums": ".../drums.wav",
        "bass": ".../bass.wav",
        "other": ".../other.wav",
    }
    """
    in_path = Path(audio_or_video_path)
    if not in_path.exists():
        raise FileNotFoundError(f"Input file not found: {audio_or_video_path}")

    target_dir = Path(output_dir) if output_dir else STEMS_DIR / in_path.stem
    target_dir.mkdir(parents=True, exist_ok=True)

    # Check if already separated
    vocal_check = target_dir / "vocals.wav"
    drums_check = target_dir / "drums.wav"
    if vocal_check.exists() and drums_check.exists():
        print(f"[Demucs] Using cached audio stems from: {target_dir}")
        return {
            "vocals": str(target_dir / "vocals.wav"),
            "drums": str(target_dir / "drums.wav"),
            "bass": str(target_dir / "bass.wav"),
            "other": str(target_dir / "other.wav"),
        }

    # If it's a video, extract temporary WAV first
    temp_wav = None
    if in_path.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".avi"):
        temp_wav = str(target_dir / "extracted_raw.wav")
        extract_audio_from_video(str(in_path), temp_wav)
        source_audio = temp_wav
    else:
        source_audio = str(in_path)

    print(f"[Demucs] Isolating audio stems using model '{model_name}'...")
    cmd = [
        sys.executable,
        "-m",
        "demucs.separate",
        "-n", model_name,
        "--out", str(STEMS_DIR),
        source_audio,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"[Demucs] Notice during separation: {e}")

    # Demucs outputs to <out>/<model>/<track_name>/
    demucs_out_folder = STEMS_DIR / model_name / Path(source_audio).stem
    results = {}
    for stem in ("vocals", "drums", "bass", "other"):
        src = demucs_out_folder / f"{stem}.wav"
        dest = target_dir / f"{stem}.wav"
        if src.exists():
            shutil.copy(src, dest)
            results[stem] = str(dest)

    # Clean up intermediate demucs folder if needed
    if demucs_out_folder.exists():
        shutil.rmtree(STEMS_DIR / model_name, ignore_errors=True)

    return results


def isolate_anime_dialogue(media_path: str, output_wav: str) -> str:
    """
    Convenience method: Extracts character screams, dialogue, and grunts
    from an anime fight clip, filtering out background music.
    """
    stems = separate_audio_stems(media_path)
    vocal_stem = stems.get("vocals")
    if vocal_stem and os.path.exists(vocal_stem):
        shutil.copy(vocal_stem, output_wav)
        return output_wav
    raise RuntimeError("Failed to isolate vocal stem from media.")
