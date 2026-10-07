"""
Z.A.I.N.E — Visual Effects & Motion Impact Engine (VFX & Style Synthesis)
Provides professional After Effects / CapCut / Alight Motion-grade anime edit presets:

Styles Supported:
1. 'velocity_flow'     : Smooth speed ramping, exponential beat-decay pulse zooms, frame-blending motion blur.
2. 'dark_phonk_impact' : Negative comic impact frames (negate), white exposure strobes, aggressive bass-drop screen shake.
3. 'manga_ink_bleed'   : High-contrast monochrome manga ink hatching that explosively shatters into saturated 60fps anime HDR.
4. 'glitch_cyberpunk'  : RGB chromatic aberration splitting, VHS scanlines, digital glitch hits on drops.
"""

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_ffmpeg_binary() -> str:
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def build_pulse_zoom_filter(
    beat_timestamps: List[float],
    base_w: int = 1080,
    base_h: int = 1920,
    zoom_intensity: float = 0.10,
    decay_rate: float = 9.0,
    window_sec: float = 0.28,
) -> str:
    """
    Generates an exponential decay spring-zoom filter synchronized to audio rhythm beats.
    On each beat drop, the screen snaps inward by zoom_intensity and smoothly springs back.
    """
    if not beat_timestamps:
        return "null"

    sampled_beats = beat_timestamps[:35]
    zoom_exprs = []
    for bt in sampled_beats:
        zoom_exprs.append(
            f"if(between(t,{bt:.2f},{bt + window_sec:.2f}),{zoom_intensity:.3f}*exp(-{decay_rate:.1f}*(t-{bt:.2f})),0)"
        )

    combined_zoom = "+".join(zoom_exprs)
    vf = (
        f"crop=w='{base_w}*(1-({combined_zoom}))':"
        f"h='{base_h}*(1-({combined_zoom}))':"
        f"x='({base_w}-out_w)/2':"
        f"y='({base_h}-out_h)/2',"
        f"scale={base_w}:{base_h}"
    )
    return vf


def build_impact_invert_filter(
    impact_timestamps: List[float],
    flash_duration: float = 0.07,
) -> str:
    """
    Produces authentic 2-3 frame negative comic impact frames ('negate') exactly on strikes.
    """
    if not impact_timestamps:
        return "null"

    conds = [f"between(t,{it:.2f},{it + flash_duration:.2f})" for it in impact_timestamps[:25]]
    active_cond = "+".join(conds)
    return f"negate=enable='{active_cond}'"


def build_impact_strobe_filter(
    beat_timestamps: List[float],
    flash_duration: float = 0.08,
    brightness: float = 0.65,
    contrast: float = 1.6,
    duration_frames: int = 3,
) -> str:
    """
    Generates an exposure flash on snare hits and explosive beat drops.
    """
    if not beat_timestamps:
        return "null"

    conds = [f"between(t,{bt:.2f},{bt + flash_duration:.2f})" for bt in beat_timestamps[:30]]
    active_cond = "+".join(conds)
    return f"eq=brightness={brightness:.2f}:contrast={contrast:.2f}:enable='{active_cond}'"


def build_screen_shake_filter(
    bass_timestamps: List[float],
    intensity: int = 15,
    duration_sec: float = 0.16,
    base_w: int = 1080,
    base_h: int = 1920,
) -> str:
    """
    Generates a high-frequency sinusoidal screen shake and camera jitter on heavy bass drops.
    """
    if not bass_timestamps:
        return "null"

    conds = [f"between(t,{bt:.2f},{bt + duration_sec:.2f})" for bt in bass_timestamps[:25]]
    active_cond = "+".join(conds)

    crop_w = base_w - (intensity * 2)
    crop_h = base_h - (intensity * 2)

    x_expr = f"({base_w}-{crop_w})/2+if({active_cond},sin(t*120)*{intensity},0)"
    y_expr = f"({base_h}-{crop_h})/2+if({active_cond},cos(t*120)*{intensity},0)"

    return f"crop=w={crop_w}:h={crop_h}:x='{x_expr}':y='{y_expr}',scale={base_w}:{base_h}"


def build_manga_ink_bleed_filter(
    drop_timestamp: float = 4.5,
    transmutation_duration: float = 0.3,
) -> str:
    """
    Build-up sequence plays in stylized high-contrast monochrome Manga ink art.
    At drop_timestamp, a flash triggers and the world explodes into saturated 60fps anime HDR.
    """
    t_drop = drop_timestamp
    t_trans = drop_timestamp + transmutation_duration

    vf = (
        f"hue=s='if(lt(t,{t_drop:.2f}),0,1.35)':"
        f"b='if(between(t,{t_drop:.2f},{t_trans:.2f}),0.70,-0.02)',"
        f"eq=contrast='if(lt(t,{t_drop:.2f}),1.65,1.25)':"
        f"saturation='if(lt(t,{t_drop:.2f}),0,1.32)',"
        f"unsharp=5:5:1.2:5:5:0.0,"
        f"vignette=PI/4.2"
    )
    return vf


def build_rgb_split_glitch_filter(
    glitch_timestamps: List[float],
    duration_sec: float = 0.10,
    offset_px: int = 14,
) -> str:
    """
    Chromatic aberration simulation: offsets the red and blue channels horizontally on glitch triggers.
    """
    if not glitch_timestamps:
        return "null"

    conds = [f"between(t,{gt:.2f},{gt + duration_sec:.2f})" for gt in glitch_timestamps[:20]]
    active_cond = "+".join(conds)

    return f"rgbashift=rh={offset_px}:bv=-{offset_px // 2}:enable='{active_cond}'"


def apply_smart_9_16_reframing(
    input_video: str,
    output_video: str,
    target_width: int = 1080,
    target_height: int = 1920,
) -> str:
    ffmpeg = get_ffmpeg_binary()
    vf = f"scale=-1:{target_height},crop={target_width}:{target_height}:(in_w-{target_width})/2:0"

    cmd = [
        ffmpeg,
        "-y",
        "-i", input_video,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "16",
        "-c:a", "copy",
        output_video,
    ]
    subprocess.run(cmd, check=True)
    return output_video


def apply_fluid_60fps_interpolation(
    input_video: str,
    output_video: str,
    target_fps: int = 60,
    crf: int = 16,
) -> str:
    ffmpeg = get_ffmpeg_binary()
    vf = f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"

    cmd = [
        ffmpeg,
        "-y",
        "-i", input_video,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", str(crf),
        "-c:a", "copy",
        output_video,
    ]
    print(f"[Fluid 60FPS] Rendering {target_fps}fps optical flow motion interpolation...")
    subprocess.run(cmd, check=True)
    return output_video


def isolate_character_subject(input_image_path: str, output_image_path: str) -> str:
    try:
        from rembg import remove
        from PIL import Image

        inp = Image.open(input_image_path)
        out = remove(inp)
        out.save(output_image_path)
        print(f"[Subject Isolation] Successfully removed background: {output_image_path}")
        return output_image_path
    except Exception as e:
        print(f"[Subject Isolation] Segmentation note: {e}")
        return input_image_path


def build_style_pipeline(
    style_name: str,
    beat_timestamps: List[float],
    impact_timestamps: Optional[List[float]] = None,
    drop_timestamp: float = 4.5,
    base_w: int = 1080,
    base_h: int = 1920,
    watermark_text: str = "ZAINE EDITZ",
) -> str:
    """
    Assembles a complete, broadcast-ready FFmpeg filter chain for the requested anime editing style.
    """
    style = style_name.lower().strip()
    impacts = impact_timestamps or beat_timestamps[::3]

    filters = []

    if style == "velocity_flow":
        filters.append(build_pulse_zoom_filter(beat_timestamps, base_w, base_h, zoom_intensity=0.11, decay_rate=9.0))
        filters.append(build_impact_strobe_filter(impacts, flash_duration=0.06, brightness=0.55, contrast=1.5))
        filters.append(build_screen_shake_filter(impacts, intensity=10, duration_sec=0.12, base_w=base_w, base_h=base_h))
        filters.append("eq=contrast=1.24:brightness=-0.02:saturation=1.35")
        filters.append("unsharp=5:5:1.1:5:5:0.0")
        filters.append("vignette=PI/4.4")

    elif style == "dark_phonk_impact":
        filters.append(build_screen_shake_filter(beat_timestamps[::2], intensity=18, duration_sec=0.18, base_w=base_w, base_h=base_h))
        filters.append(build_pulse_zoom_filter(beat_timestamps, base_w, base_h, zoom_intensity=0.14, decay_rate=11.0))
        filters.append(build_impact_invert_filter(impacts, flash_duration=0.07))
        filters.append(build_impact_strobe_filter(beat_timestamps[1::2], flash_duration=0.07, brightness=0.70, contrast=1.7))
        filters.append("eq=contrast=1.32:brightness=-0.03:saturation=1.38")
        filters.append("unsharp=5:5:1.25:5:5:0.0")
        filters.append("vignette=PI/4.0")

    elif style == "manga_ink_bleed":
        filters.append(build_manga_ink_bleed_filter(drop_timestamp=drop_timestamp))
        post_drop_beats = [b for b in beat_timestamps if b >= drop_timestamp]
        filters.append(build_pulse_zoom_filter(post_drop_beats, base_w, base_h, zoom_intensity=0.12, decay_rate=8.5))
        filters.append(build_screen_shake_filter([b for b in impacts if b >= drop_timestamp], intensity=14, base_w=base_w, base_h=base_h))

    elif style in ("combined_hybrid", "combined", "hybrid", "hybrid_master"):
        # 1. Manga Seriousness Ink Frames (Monochrome high contrast on build-up/tension)
        serious_cond = f"between(t,0,{drop_timestamp:.2f})"
        filters.append(f"hue=s='if({serious_cond},0,1.35)':b='if({serious_cond},-0.04,-0.02)'")
        filters.append(f"eq=contrast='if({serious_cond},1.70,1.26)':saturation='if({serious_cond},0,1.32)'")

        # 2. RGB Chromatic Aberration Glitch when hits land on characters
        if impacts:
            glitch_conds = [f"between(t,{it:.2f},{it + 0.10:.2f})" for it in impacts[:20]]
            filters.append(f"rgbashift=rh=16:bv=-8:enable='{'+'.join(glitch_conds)}'")

        # 3. Negative Comic Impact Frame on climax hit
        if impacts:
            climax_hit = impacts[len(impacts) // 2] if len(impacts) > 1 else impacts[0]
            filters.append(f"negate=enable='between(t,{climax_hit:.2f},{climax_hit + 0.07:.2f})'")

        # 4. Exposure strobe flash on beat drop
        strobe_conds = [f"between(t,{bt:.2f},{bt + 0.07:.2f})" for bt in beat_timestamps[::2][:15]]
        if strobe_conds:
            filters.append(f"eq=brightness=0.65:contrast=1.65:enable='{'+'.join(strobe_conds)}'")

        # 5. Beat-synced Pulse Zoom & Screen Shake combined
        filters.append(build_pulse_zoom_filter(beat_timestamps, base_w, base_h, zoom_intensity=0.12, decay_rate=9.0))
        filters.append(build_screen_shake_filter(impacts, intensity=14, duration_sec=0.15, base_w=base_w, base_h=base_h))

        # 6. Ultra-crisp grading
        filters.append("unsharp=5:5:1.15:5:5:0.0")
        filters.append("vignette=PI/4.3")

    elif style == "glitch_cyberpunk":
        filters.append(build_rgb_split_glitch_filter(beat_timestamps[::2], duration_sec=0.10, offset_px=14))
        filters.append(build_pulse_zoom_filter(beat_timestamps, base_w, base_h, zoom_intensity=0.10))
        filters.append(build_impact_strobe_filter(impacts, flash_duration=0.06, brightness=0.60, contrast=1.6))
        filters.append("eq=contrast=1.26:brightness=-0.02:saturation=1.40")
        filters.append("unsharp=5:5:1.15:5:5:0.0")
        filters.append("vignette=PI/4.3")

    else:
        filters.append(build_pulse_zoom_filter(beat_timestamps[:20], base_w, base_h, zoom_intensity=0.08))
        filters.append("eq=contrast=1.22:brightness=-0.02:saturation=1.32")
    # Dynamic Learned Technique Injection from data/editing_knowledge.json
    try:
        import json
        knowledge_file = PROJECT_ROOT / "data" / "editing_knowledge.json"
        if knowledge_file.exists():
            with open(knowledge_file, "r", encoding="utf-8") as kf:
                knowledge = json.load(kf)
                # If requested style is a specific learned technique
                if style in knowledge and "ffmpeg_filter_snippet" in knowledge[style]:
                    snippet = knowledge[style]["ffmpeg_filter_snippet"]
                    if snippet and snippet != "null":
                        filters.append(snippet)
                # Or inject any active production preset learned recently
                for k, v in knowledge.items():
                    if isinstance(v, dict) and v.get("status") == "ACTIVE_PRODUCTION_PRESET":
                        if k in style or style == "combined_hybrid":
                            snip = v.get("ffmpeg_filter_snippet")
                            if snip and snip not in filters:
                                filters.append(snip)
    except Exception:
        pass

    # Sleek typography overlays
    safe_watermark = watermark_text.replace(":", "\\:").replace("'", "\\'")
    filters.append(
        f"drawtext=text='{safe_watermark}':fontsize=44:fontcolor=0x00F0FF:bordercolor=black:borderw=3:x=60:y=h-240"
    )
    filters.append(
        "drawtext=text='ZAINE STUDIO':fontsize=26:fontcolor=0xFFD700:bordercolor=black:borderw=2:x=w-260:y=140"
    )

    active_filters = [f for f in filters if f and f != "null"]
    return ",".join(active_filters)
