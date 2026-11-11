---
name: youtube-video-editing
description: Professional YouTube video editing, timeline automation, FFmpeg filtering, pacing optimization, audio mastering, subtitle synchronization, and viral Shorts formatting. Use when generating, cutting, pacing, or publishing video content.
---

# YouTube Video Editing & Production Mastery

Specialized multimedia production capability for automated timeline generation, audio engineering, visual pacing, subtitle rendering, and YouTube algorithm optimization.

## Core Capabilities

1. **Timeline Composition & Cut Automation**:
   - Pacing algorithms: 1.5s–3.0s visual pattern interruption for YouTube Shorts; 4s–7s cadence for long-form tutorials.
   - Silence and filler word removal via audio waveform gating (`silenceremove` filter).
   - Export multi-track edit timelines to FCPXML, EDL, and CapCut JSON formats.

2. **Audio Engineering & Stems Mastering**:
   - Neural stem separation (vocals, bass, drums, accompaniment) via Meta Demucs.
   - Target YouTube broadcast audio standards: -14 LUFS integrated loudness, -1.0 dB true peak.
   - Dialogue ducking: automatically attenuate background BGM by 12–18 dB during spoken sentences.

3. **Subtitles & Typography Dynamics**:
   - Dynamic animated subtitle styling (word-by-word highlight, ASS/SSA karaoke tags, punchy neon strokes).
   - Safe margin compliance: 1080x1920 (9:16) title-safe zones avoiding YouTube UI buttons.

4. **FFmpeg Command Generation**:
   - Complex filtergraphs (`filter_complex`) for crossfades, scaling, color grading (LUT application), picture-in-picture, and audio normalization.

