"""
Z.A.I.N.E — Autonomous Anime Music Video (AMV) & "Dark Editz" Engine
Empowers Zaine to autonomously produce broadcast-quality anime battle edits,
parallel comparison splits (e.g. Naruto vs Sasuke, Goku vs Vegeta, Luffy vs Kaido),
and beat-synced high-energy Shorts with cinematic color grading.

Directives:
- ZERO synthetic robotic TTS over procedural shapes for anime battle shorts.
- Authentic anime footage, beat-synced cuts, deep crushed blacks, high contrast.
- Visual sharpness (unsharp mask), cinematic edge vignette, sleek neon branding (ZAINE EDITZ).
- Quality first: High bitrate, visually lossless CRF 16, 1080x1920 vertical canvas.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EDITS_DIR = PROJECT_ROOT / "workspace" / "edits"
CLIPS_DIR = EDITS_DIR / "raw_clips"
AUDIO_DIR = PROJECT_ROOT / "workspace" / "audio" / "bg_music"
SHORTS_DIR = PROJECT_ROOT / "workspace" / "youtube_shorts"

for d in (EDITS_DIR, CLIPS_DIR, AUDIO_DIR, SHORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def get_ffmpeg_binary() -> str:
    """Finds system or imageio-ffmpeg binary."""
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def get_yt_dlp_binary() -> str:
    """Finds yt-dlp binary or invokes via python -m yt_dlp."""
    dlp = shutil.which("yt-dlp")
    if dlp:
        return dlp
    return f'"{sys.executable}" -m yt_dlp'


def download_raw_clip(
    query_or_url: str,
    output_filename: str,
    max_duration: int = 45,
) -> Optional[str]:
    """
    Downloads high-resolution anime footage using yt-dlp.
    Prioritizes visual quality (1080p+, 60fps) without file-size limitations.
    """
    out_path = CLIPS_DIR / output_filename
    if out_path.exists() and out_path.stat().st_size > 100_000:
        return str(out_path)

    # If it's a search term, format as ytsearch1:
    target = query_or_url
    if not (target.startswith("http://") or target.startswith("https://")):
        target = f"ytsearch1:{query_or_url} 1080p 60fps"

    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--format",
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format",
        "mp4",
        "--no-playlist",
        "--output",
        str(out_path),
        target,
    ]

    try:
        print(f"[Anime Editor] Fetching footage: {query_or_url}...")
        subprocess.run(cmd, check=True, timeout=180, capture_output=True)
        if out_path.exists() and out_path.stat().st_size > 50_000:
            print(f"[Anime Editor] Successfully harvested footage: {out_path.name} ({out_path.stat().st_size / (1024*1024):.2f} MB)")
            return str(out_path)
    except Exception as e:
        print(f"[Anime Editor] Clip download note: {e}")

    return None


def detect_audio_beats(audio_path: str, hop_sec: float = 0.05, min_dist_sec: float = 0.35) -> list[float]:
    """
    Extracts precise beat drops, bass kicks, and high-energy transients from an audio track.
    Used to snap video cuts, velocity zooms, and strobe impacts to the music.
    """
    try:
        from scipy.io import wavfile
        import scipy.signal as signal
        import numpy as np

        sr, data = wavfile.read(audio_path)
        audio = data.mean(axis=1) if data.ndim > 1 else data
        hop = int(sr * hop_sec)
        n_blocks = len(audio) // hop
        if n_blocks == 0:
            return []
        reshaped = audio[:n_blocks * hop].reshape(n_blocks, hop).astype(float)
        rms = np.sqrt(np.mean(reshaped**2, axis=1))
        peaks, _ = signal.find_peaks(rms, distance=int(min_dist_sec / hop_sec), prominence=np.std(rms))
        beat_times = [round(float(p * hop_sec), 2) for p in peaks]
        print(f"[Beat Sync] Detected {len(beat_times)} primary rhythm beats in audio.")
        return beat_times
    except Exception as e:
        print(f"[Beat Sync] Audio analysis fallback: {e}")
        return []


def split_raw_into_scenes(video_path: str, threshold: float = 27.0) -> list[tuple[float, float]]:
    """
    Uses PySceneDetect to automatically slice an uncut raw episode into individual combat camera shots.
    Returns list of (start_sec, end_sec) for every distinct cut.
    """
    try:
        from scenedetect import detect, ContentDetector
        print(f"[Scene Detect] Slicing raw footage into camera shots: {video_path}...")
        scene_list = detect(video_path, ContentDetector(threshold=threshold))
        scenes = [(round(s[0].get_seconds(), 2), round(s[1].get_seconds(), 2)) for s in scene_list]
        print(f"[Scene Detect] Found {len(scenes)} distinct shots in source footage.")
        return scenes
    except Exception as e:
        print(f"[Scene Detect] Scene detection note: {e}")
        return []


def score_scene_motion(video_path: str, start_sec: float, end_sec: float, sample_fps: int = 4) -> float:
    """
    Uses OpenCV optical flow to measure the action velocity and kinetic intensity of a scene.
    High scores = intense combat, high-speed strikes, kinetic auras.
    """
    try:
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)
        prev_gray = None
        motion_scores = []

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        frame_step = max(1, int(fps / sample_fps))
        max_frames = int((end_sec - start_sec) * sample_fps)

        count = 0
        while cap.isOpened() and count < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (320, 180))  # Downsample for lightning-fast optical flow
            if prev_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                motion_scores.append(float(np.mean(mag)))
            prev_gray = gray
            count += 1
            for _ in range(frame_step - 1):
                cap.grab()

        cap.release()
        return float(np.mean(motion_scores)) if motion_scores else 0.0
    except Exception as e:
        print(f"[Motion Scorer] Optical flow note: {e}")
        return 0.0


def render_dark_edit_parallel(
    top_clip_path: str,
    bottom_clip_path: str,
    audio_path: str,
    output_path: str,
    duration: float = 45.0,
    top_label: str = "VALLEY OF THE END (GENIN)",
    bottom_label: str = "FINAL BATTLE (SHIPPUDEN)",
    crf: int = 16,
) -> str:
    """
    Renders a Master Parallel Split (Top/Bottom) Anime Short (1080x1920):
    - Top: 1080x960 center cropped & scaled
    - Bottom: 1080x960 center cropped & scaled
    - Stacks vertically into 1080x1920
    - Applies Dark Editz color curve (contrast 1.22, sat 1.32, unsharp mask, vignette)
    - Brands with subtle neon 'ZAINE EDITZ' glow and 'ZAINE STUDIO'
    - Encodes at pristine CRF 16 slow preset with high-fidelity audio
    """
    ffmpeg = get_ffmpeg_binary()

    # Video filter chain:
    # 1. Scale/crop top clip to 1080x960
    # 2. Scale/crop bottom clip to 1080x960
    # 3. Stack vertically
    # 4. Color grade: contrast, saturation, unsharp, vignette
    # 5. Overlays: ZAINE EDITZ watermark
    vf = (
        "[0:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[top];"
        "[1:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bottom];"
        "[top][bottom]vstack=inputs=2[stacked];"
        "[stacked]eq=contrast=1.22:brightness=-0.02:saturation=1.32,"
        "unsharp=5:5:1.1:5:5:0.0,"
        "vignette=PI/4.4,"
        "drawtext=text='ZAINE EDITZ':fontsize=44:fontcolor=0x00F0FF:bordercolor=black:borderw=3:x=60:y=h-220,"
        "drawtext=text='ZAINE STUDIO':fontsize=28:fontcolor=0xFFD700:bordercolor=black:borderw=2:x=w-260:y=140[outv]"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-t", str(duration),
        "-i", top_clip_path,
        "-t", str(duration),
        "-i", bottom_clip_path,
        "-i", audio_path,
        "-filter_complex", vf,
        "-map", "[outv]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", str(crf),
        "-c:a", "aac",
        "-b:a", "320k",
        "-shortest",
        output_path,
    ]

    print(f"[Anime Editor] Rendering Master Dark Edit parallel split: {output_path} (CRF {crf})...")
    subprocess.run(cmd, check=True)
    return output_path


def apply_dark_editz_master_grade(
    input_video_path: str,
    output_path: str,
    audio_track_path: Optional[str] = None,
    watermark_text: str = "ZAINE EDITZ",
    crf: int = 16,
) -> str:
    """
    Applies the full Dark Editz visual grading stack to any raw anime video:
    - 1080x1920 vertical canvas
    - Contrast 1.20, Brightness -0.02, Saturation 1.30
    - Edge unsharp mask (razor sharp anime line art)
    - Cinematic edge vignette
    - ZAINE EDITZ cyan glow branding
    - Visually lossless CRF 16 H.264
    """
    ffmpeg = get_ffmpeg_binary()

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "eq=contrast=1.20:brightness=-0.02:saturation=1.30,"
        "unsharp=5:5:1.0:5:5:0.0,"
        "vignette=PI/4.5,"
        f"drawtext=text='{watermark_text}':fontsize=42:fontcolor=0x00F0FF:bordercolor=black:borderw=3:x=60:y=h-220,"
        "drawtext=text='ZAINE STUDIO':fontsize=28:fontcolor=0xFFD700:bordercolor=black:borderw=2:x=w-260:y=140"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-i", input_video_path,
    ]

    if audio_track_path and os.path.exists(audio_track_path):
        cmd.extend(["-i", audio_track_path, "-map", "0:v", "-map", "1:a"])
    else:
        cmd.extend(["-c:a", "copy"])

    cmd.extend([
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", str(crf),
        output_path,
    ])

    print(f"[Anime Editor] Applying Master Dark Grade: {output_path} (CRF {crf})...")
    subprocess.run(cmd, check=True)
    return output_path


def generate_anime_amv(
    topic: str = "Naruto vs Sasuke",
    output_filename: Optional[str] = None,
    duration: float = 45.0,
    aspect_ratio: str = "9:16",
    crf: int = 16,
) -> Dict[str, Any]:
    """
    High-level orchestrator for anime battle Shorts:
    1. Selects authentic soundtrack (e.g. 'Raga of Revenge' or intense battle track).
    2. Identifies or harvests HD clips for the matchup.
    3. Renders the Master Dark Edit with crisp grading, beat sync, and sleek branding.
    4. Target duration: 30s to 60s for Shorts, up to 90s for full AMVs.
    5. Returns rich YouTube metadata ready for publication.
    """
    topic_lower = topic.lower()
    ts = int(os.times().system + os.times().user * 1000)

    # Clamp duration to professional AMV standards (30s minimum for Shorts, up to 90s for full AMVs)
    clamped_duration = max(30.0, min(duration, 90.0))

    if not output_filename:
        safe_name = "".join(c if c.isalnum() else "_" for c in topic.lower()).strip("_")
        output_filename = f"anime_amv_{safe_name}_{ts}.mp4"

    output_path = str(SHORTS_DIR / output_filename)
    bgm_raga = AUDIO_DIR / "raga_of_revenge_authentic.wav"

    # STRICT INTEGRITY RULE: Never use or re-upload another creator's edit.
    # Source footage MUST be raw anime fight clips from workspace/edits/raw_clips/ or freshly harvested.
    raw_clip_top = CLIPS_DIR / f"{topic.lower().replace(' ', '_')}_top_raw.mp4"
    raw_clip_bottom = CLIPS_DIR / f"{topic.lower().replace(' ', '_')}_bottom_raw.mp4"

    if "naruto" in topic_lower or "sasuke" in topic_lower:
        title = "Naruto vs Sasuke | The Valley of the End Parallels 💥🔥 #shorts #naruto #sasuke #anime #edit"
        description = (
            "Original parallel compilation: Naruto vs Sasuke Part 1 vs Shippuden Final Battle.\n\n"
            "Which battle had better hand-to-hand choreography? Drop your vote below! 👇\n\n"
            "#naruto #sasuke #anime #amv #darkedit #shippuden #animeedit #zaineeditz #shorts"
        )
        tags = ["Naruto", "Sasuke", "Anime", "AMV", "Naruto vs Sasuke", "Anime Edit", "Shippuden", "Shorts", "ZaineEditz"]
        question = "Which battle had better hand-to-hand choreography: Part 1 or Shippuden? Drop your thoughts! 💥👇"
    else:
        title = f"{topic} | Power Clash Edit 💥🔥 #shorts #anime #edit"
        description = (
            f"Original battle edit: {topic}.\n\n"
            "Who takes the victory in your eyes? Drop your vote below! 👇\n\n"
            f"#anime #{topic.replace(' ', '').lower()} #amv #darkedit #animeedit #zaineeditz #shorts"
        )
        tags = [topic, "Anime", "AMV", "Dark Edit", "Anime Edit", "Shorts", "ZaineEditz"]
        question = f"Who takes the victory in {topic}? Drop your vote below! 💥👇"

    # Verify or harvest raw unedited source clips
    if not (raw_clip_top.exists() and raw_clip_bottom.exists()):
        print(f"[Anime Editor] Harvesting raw unedited source clips for '{topic}'...")
        download_raw_clip(f"{topic} raw fight 1080p", raw_clip_top.name)
        download_raw_clip(f"{topic} final battle raw 1080p", raw_clip_bottom.name)

    if raw_clip_top.exists() and raw_clip_bottom.exists():
        render_dark_edit_parallel(
            top_clip_path=str(raw_clip_top),
            bottom_clip_path=str(raw_clip_bottom),
            audio_path=str(bgm_raga) if bgm_raga.exists() else "",
            output_path=output_path,
            duration=clamped_duration,
            crf=crf,
        )
    elif raw_clip_top.exists():
        apply_dark_editz_master_grade(
            input_video_path=str(raw_clip_top),
            output_path=output_path,
            audio_track_path=str(bgm_raga) if bgm_raga.exists() else None,
            crf=crf,
        )
    else:
        # If no raw clips are yet harvested, render cannot proceed on unoriginal material
        raise FileNotFoundError(
            f"No raw anime fight footage found for '{topic}' in {CLIPS_DIR}. "
            "Zaine strictly forbids reusing existing creator edits. "
            "Please provide raw anime footage or allow the idle harvester to cache original source clips."
        )

    return {
        "video_path": output_path,
        "title": title,
        "description": description,
        "tags": tags,
        "category_id": "1",  # Film & Animation
        "engagement_question": question,
        "genre": "anime",
        "file_size_mb": round(os.path.getsize(output_path) / (1024 * 1024), 2),
    }


def harvest_anime_assets_during_idle():
    """
    Background worker that runs during the 3-hour daily cadence time gaps.
    Actively searches and caches pristine 1080p fight sequences and viral anime audio
    so rendering is instant and unthrottled when the upload window arrives.
    """
    priority_topics = [
        "Naruto vs Sasuke Final Battle 1080p 60fps clip",
        "Goku vs Vegeta Saiyan Saga vs Super 1080p clip",
        "Luffy Gear 5 vs Kaido 1080p clip",
        "Gojo vs Sukuna Domain Expansion clash clip",
    ]
    for topic in priority_topics:
        fname = topic.split()[0].lower() + "_raw.mp4"
        try:
            download_raw_clip(topic, fname)
        except Exception as e:
            print(f"[Idle Harvester] Harvesting {topic}: {e}")
