"""
Z.A.I.N.E — Professional Timeline Exporter (CapCut Pro / Premiere / DaVinci Resolve)
Exports Zaine's beat-synchronized anime cuts and markers into industry-standard formats:
- Apple Final Cut Pro XML (.fcpxml) — Native import in CapCut Pro, Adobe Premiere Pro, and DaVinci Resolve.
- CMX 3600 Edit Decision List (.edl) — Supported by every major Non-Linear Editor.
- Beat Marker CSV (.csv) — Instant music marker imports.

Use cases:
1. Zaine cuts an entire 1-3 minute AMV on the beat.
2. User can immediately open the project in CapCut Pro or Premiere to adjust keyframes or add custom 3D text.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TIMELINES_DIR = PROJECT_ROOT / "workspace" / "timelines"
TIMELINES_DIR.mkdir(parents=True, exist_ok=True)


def export_edl_timeline(
    clips: List[Dict[str, Any]],
    output_edl_path: str,
    fps: float = 30.0,
    title: str = "ZAINE_ANIME_AMV",
) -> str:
    """
    Generates a CMX 3600 Edit Decision List (.edl).
    clips: [
        {"source_path": ".../clip1.mp4", "src_in": 0.0, "src_out": 2.5, "dst_in": 0.0, "dst_out": 2.5},
        ...
    ]
    """
    def sec_to_tc(sec: float, frame_rate: float) -> str:
        total_frames = int(round(sec * frame_rate))
        f = total_frames % int(frame_rate)
        total_sec = total_frames // int(frame_rate)
        s = total_sec % 60
        total_min = total_sec // 60
        m = total_min % 60
        h = total_min // 60
        return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"

    lines = [
        f"TITLE: {title}",
        "FCM: NON-DROP FRAME",
        "",
    ]

    for idx, clip in enumerate(clips, 1):
        reel = f"AX{idx:03d}"
        src_in_tc = sec_to_tc(clip.get("src_in", 0.0), fps)
        src_out_tc = sec_to_tc(clip.get("src_out", 1.0), fps)
        dst_in_tc = sec_to_tc(clip.get("dst_in", 0.0), fps)
        dst_out_tc = sec_to_tc(clip.get("dst_out", 1.0), fps)

        lines.append(f"{idx:03d}  {reel:<8} V     C        {src_in_tc} {src_out_tc} {dst_in_tc} {dst_out_tc}")
        src_name = Path(clip.get("source_path", "clip")).name
        lines.append(f"* FROM CLIP NAME: {src_name}")
        lines.append("")

    with open(output_edl_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[Timeline Exporter] Exported CMX 3600 EDL to: {output_edl_path}")
    return output_edl_path


def export_fcpxml_timeline(
    clips: List[Dict[str, Any]],
    output_fcpxml_path: str,
    audio_path: Optional[str] = None,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    title: str = "Zaine Dark Edit",
) -> str:
    """
    Generates an Apple Final Cut Pro XML (.fcpxml v1.9).
    Directly importable by:
    - CapCut Pro (File -> Import -> XML)
    - Adobe Premiere Pro (File -> Import -> FCP XML)
    - DaVinci Resolve (File -> Import -> Timeline -> FCP XML)
    """
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE fcpxml>',
        '<fcpxml version="1.9">',
        '    <resources>',
        f'        <format id="r1" frameDuration="1/{fps}s" width="{width}" height="{height}"/>',
    ]

    # Register assets
    all_sources = list({c.get("source_path") for c in clips if c.get("source_path")})
    if audio_path:
        all_sources.append(audio_path)

    asset_ids = {}
    for i, src in enumerate(all_sources, 2):
        asset_id = f"r{i}"
        asset_ids[src] = asset_id
        src_uri = Path(src).resolve().as_uri()
        src_name = Path(src).name
        xml_lines.append(f'        <asset id="{asset_id}" name="{src_name}" src="{src_uri}"/>')

    xml_lines.extend([
        '    </resources>',
        '    <library>',
        f'        <event name="{title}">',
        f'            <project name="{title}">',
        '                <sequence format="r1">',
        '                    <spine>',
    ])

    # Append clips on primary storyline
    for clip in clips:
        src = clip.get("source_path")
        asset_id = asset_ids.get(src, "r2")
        duration = clip.get("src_out", 1.0) - clip.get("src_in", 0.0)
        dur_str = f"{int(duration * fps)}/{fps}s"
        start_str = f"{int(clip.get('src_in', 0.0) * fps)}/{fps}s"
        clip_name = Path(src).stem if src else "clip"

        xml_lines.append(
            f'                        <asset-clip ref="{asset_id}" name="{clip_name}" duration="{dur_str}" start="{start_str}"/>'
        )

    xml_lines.extend([
        '                    </spine>',
        '                </sequence>',
        '            </project>',
        '        </event>',
        '    </library>',
        '</fcpxml>',
    ])

    with open(output_fcpxml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(xml_lines))

    print(f"[Timeline Exporter] Exported CapCut/Premiere FCPXML to: {output_fcpxml_path}")
    return output_fcpxml_path


def export_beat_markers_csv(
    beat_timestamps: List[float],
    output_csv_path: str,
    fps: float = 30.0,
) -> str:
    """
    Generates a CSV of beat markers importable into Premiere / DaVinci Resolve.
    """
    lines = ["Name,Start,Duration,Timecode,Description"]
    for i, bt in enumerate(beat_timestamps, 1):
        total_frames = int(round(bt * fps))
        f = total_frames % int(fps)
        total_sec = total_frames // int(fps)
        s = total_sec % 60
        m = (total_sec // 60) % 60
        h = total_sec // 3600
        tc = f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
        lines.append(f"Beat_{i},{bt:.2f},0.10,{tc},Heavy Drop")

    with open(output_csv_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[Timeline Exporter] Exported Beat Markers CSV to: {output_csv_path}")
    return output_csv_path
