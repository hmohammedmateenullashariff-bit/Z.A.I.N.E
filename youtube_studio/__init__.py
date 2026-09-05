"""
Z.A.I.N.E — YouTube Autonomous Content & Channel Studio
Provides end-to-end automated YouTube Shorts generation, resumable uploading,
real-time channel analytics, and daily 2:00 PM - 5:00 PM scheduled automation.
"""

from .content_generator import generate_youtube_short
from .uploader import upload_youtube_video, get_upload_queue
from .analytics import get_channel_analytics, format_analytics_dossier
from .scheduler import check_and_run_daily_youtube_schedule, get_studio_status
from .anime_editor import generate_anime_amv, harvest_anime_assets_during_idle, detect_audio_beats, split_raw_into_scenes, score_scene_motion
from .audio_separator import separate_audio_stems, isolate_anime_dialogue
from .timeline_exporter import export_fcpxml_timeline, export_edl_timeline, export_beat_markers_csv
from .fx_engine import build_impact_strobe_filter, build_screen_shake_filter, apply_fluid_60fps_interpolation, apply_smart_9_16_reframing
from .video_ai_hub import generate_action_scene, get_available_video_providers

__all__ = [
    "generate_youtube_short",
    "upload_youtube_video",
    "get_upload_queue",
    "get_channel_analytics",
    "format_analytics_dossier",
    "check_and_run_daily_youtube_schedule",
    "get_studio_status",
    "generate_anime_amv",
    "harvest_anime_assets_during_idle",
    "detect_audio_beats",
    "split_raw_into_scenes",
    "score_scene_motion",
    "separate_audio_stems",
    "isolate_anime_dialogue",
    "export_fcpxml_timeline",
    "export_edl_timeline",
    "export_beat_markers_csv",
    "build_impact_strobe_filter",
    "build_screen_shake_filter",
    "apply_fluid_60fps_interpolation",
    "apply_smart_9_16_reframing",
    "generate_action_scene",
    "get_available_video_providers",
]


