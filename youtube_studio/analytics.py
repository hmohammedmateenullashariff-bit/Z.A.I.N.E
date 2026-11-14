"""
Z.A.I.N.E — YouTube Autonomous Analytics & Channel Growth Tracker
Queries channel metrics, tracks 24-hour subscriber/view deltas,
and generates formatted executive growth dossiers for Telegram and voice.
"""

import os
import re
import html
import json
import datetime
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYTICS_HISTORY = PROJECT_ROOT / "data" / "youtube_analytics_history.json"
QUEUE_FILE = PROJECT_ROOT / "data" / "youtube_queue.json"
ARCHIVE_FILE = PROJECT_ROOT / "data" / "youtube_queue_archive.json"


def _iter_youtube_auth_modes(channel_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Builds ordered YouTube Data API v3 auth contexts (OAuth2 first, API key fallback)."""
    from .uploader import get_stored_token, refresh_access_token

    modes: List[Dict[str, Any]] = []
    token_data = get_stored_token()
    if token_data and (token_data.get("access_token") or token_data.get("token") or token_data.get("refresh_token")):
        access_token = refresh_access_token(token_data) or token_data.get("token")
        if access_token:
            modes.append({
                "headers": {"Authorization": f"Bearer {access_token}"},
                "channel_query": "mine=true",
                "key_param": "",
                "source": "YouTube Data API (OAuth2)",
            })

    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if api_key and channel_id:
        modes.append({
            "headers": {},
            "channel_query": f"id={channel_id}&key={api_key}",
            "key_param": f"&key={api_key}",
            "source": "YouTube Data API (Key)",
        })
    return modes


def get_channel_analytics(channel_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches real-time channel statistics via YouTube Data API v3.
    Falls back to local studio metrics if API credentials are not yet linked.
    """
    for auth in _iter_youtube_auth_modes(channel_id=channel_id):
        url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet&{auth['channel_query']}"
        try:
            resp = requests.get(url, headers=auth["headers"], timeout=15)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                if items:
                    ch = items[0]
                    snippet = ch.get("snippet", {})
                    stats = ch.get("statistics", {})
                    return _record_analytics_snapshot({
                        "connected": True,
                        "channel_title": snippet.get("title", "Project Z Studio"),
                        "custom_url": snippet.get("customUrl", ""),
                        "subscribers": int(stats.get("subscriberCount", 0)),
                        "total_views": int(stats.get("viewCount", 0)),
                        "total_videos": int(stats.get("videoCount", 0)),
                        "source": auth["source"],
                    })
                if auth["source"] == "YouTube Data API (OAuth2)":
                    return _record_analytics_snapshot({
                        "connected": True,
                        "channel_title": "Authenticated Google Account",
                        "custom_url": "",
                        "subscribers": 0,
                        "total_views": 0,
                        "total_videos": 0,
                        "notice": "Google OAuth is active! If your channel has not been initialized yet, visit https://www.youtube.com/create_channel to set your channel name.",
                        "source": auth["source"],
                    })
        except Exception as e:
            print(f"[YouTube Analytics] {auth['source']} request error: {e}")

    # Fallback: Local Studio Production Statistics
    from .uploader import get_upload_queue
    queue = get_upload_queue()
    published = sum(1 for q in queue if q.get("status") == "PUBLISHED")
    queued = sum(1 for q in queue if q.get("status") in ("QUEUED", "QUEUED_PENDING_AUTH"))

    return {
        "connected": False,
        "channel_title": "Project Z AI Studio (Local Production)",
        "subscribers": 0,
        "total_views": 0,
        "total_videos": published,
        "local_queue_count": queued,
        "local_published_count": published,
        "notice": "Link Google OAuth client_secret.json to sync live channel subscribers and view metrics.",
        "source": "Local Studio Queue",
    }


def _record_analytics_snapshot(current_stats: Dict[str, Any]) -> Dict[str, Any]:
    """Records daily snapshot to compute 24-hour deltas."""
    today_str = datetime.date.today().isoformat()
    history = {}

    if ANALYTICS_HISTORY.exists():
        try:
            with open(ANALYTICS_HISTORY, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    prev_day_str = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    prev_snapshot = history.get(prev_day_str, {})

    delta_subs = current_stats["subscribers"] - prev_snapshot.get("subscribers", current_stats["subscribers"])
    delta_views = current_stats["total_views"] - prev_snapshot.get("total_views", current_stats["total_views"])

    current_stats["delta_subscribers_24h"] = delta_subs
    current_stats["delta_views_24h"] = delta_views
    current_stats["last_updated"] = datetime.datetime.now().isoformat()

    history[today_str] = {
        "subscribers": current_stats["subscribers"],
        "total_views": current_stats["total_views"],
        "total_videos": current_stats["total_videos"],
        "timestamp": current_stats["last_updated"],
    }

    ANALYTICS_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with open(ANALYTICS_HISTORY, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    return current_stats


def format_analytics_dossier(stats: Optional[Dict[str, Any]] = None) -> str:
    """Formats an executive Markdown dossier for Mateen."""
    if stats is None:
        stats = get_channel_analytics()

    lines = [
        f"### 📈 YouTube Studio Intelligence: `{stats['channel_title']}`",
        f"**Live Status**: {'🟢 Connected to Channel' if stats.get('connected') else '🟡 Local Studio Mode'}",
    ]

    if stats.get("connected"):
        delta_subs = stats.get("delta_subscribers_24h", 0)
        delta_views = stats.get("delta_views_24h", 0)
        sub_sign = f"+{delta_subs}" if delta_subs > 0 else str(delta_subs)
        view_sign = f"+{delta_views}" if delta_views > 0 else str(delta_views)

        lines.extend([
            f"• **Channel Subscribers**: `{stats['subscribers']:,}` ({sub_sign} in 24h)",
            f"• **Lifetime Channel Views**: `{stats['total_views']:,}` ({view_sign} in 24h)",
            f"• **Published Videos**: `{stats['total_videos']}` videos",
        ])
    else:
        lines.extend([
            f"• **Rendered Shorts in Queue**: `{stats.get('local_queue_count', 0)}` ready for upload",
            f"• **Published Videos**: `{stats.get('local_published_count', 0)}`",
            f"• **Authentication**: {stats.get('notice')}",
        ])

    return "\n".join(lines)


def get_spoken_analytics_brief() -> str:
    """Generates a concise spoken summary for Zaine's neural voice."""
    stats = get_channel_analytics()
    if stats.get("connected"):
        subs = stats["subscribers"]
        views = stats["total_views"]
        return f"Sir, here is your YouTube Studio update: Your channel currently has {subs} subscribers and {views} lifetime views across {stats['total_videos']} published videos."
    else:
        queue_count = stats.get("local_queue_count", 0)
        return f"Sir, your YouTube Studio has {queue_count} rendered AI Shorts queued in the workspace and ready for upload."


_ISO_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def _parse_iso8601_duration(duration_str: str) -> int:
    """Converts YouTube ISO-8601 duration (e.g. 'PT1M12S') to whole seconds."""
    if not duration_str:
        return 0
    match = _ISO_DURATION_RE.match(str(duration_str).strip())
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def _format_duration_label(seconds: int) -> str:
    """Formats video duration seconds into compact human-readable form."""
    if seconds <= 0:
        return ""
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _parse_timestamp_sort_key(ts_str: str) -> float:
    """Converts ISO/RFC3339 timestamps to epoch seconds for newest-first sorting."""
    raw = str(ts_str or "").strip()
    if not raw:
        return 0.0
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.datetime.now().astimezone().tzinfo)
        return dt.timestamp()
    except Exception:
        return 0.0


def _format_published_timestamp(ts_str: str) -> str:
    """Formats an ISO/RFC3339 timestamp into local 'YYYY-MM-DD HH:MM'."""
    raw = str(ts_str or "").strip()
    if not raw:
        return "Unknown time"
    try:
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.datetime.fromisoformat(normalized)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return raw[:16].replace("T", " ")


def _build_video_url(video_id: str, title: str = "", duration_sec: int = 0) -> str:
    """Constructs the canonical Shorts or watch URL for a YouTube video ID."""
    if not video_id:
        return ""
    is_short = (0 < duration_sec <= 60) or ("short" in str(title or "").lower())
    return f"https://youtube.com/shorts/{video_id}" if is_short else f"https://youtube.com/watch?v={video_id}"


def _normalize_video_entry(entry: Dict[str, Any], *, from_api: bool = False) -> Optional[Dict[str, Any]]:
    """Normalizes a local or YouTube Data API video entry into a common report shape."""
    if not isinstance(entry, dict):
        return None

    if from_api:
        video_id = str(entry.get("id", "")).strip()
        snippet = entry.get("snippet", {}) or {}
        stats = entry.get("statistics", {}) or {}
        status_obj = entry.get("status", {}) or {}
        content_details = entry.get("contentDetails", {}) or {}
        title = str(snippet.get("title") or "Untitled Video").strip()
        duration_sec = _parse_iso8601_duration(content_details.get("duration", ""))
        published_at = str(content_details.get("videoPublishedAt") or snippet.get("publishedAt") or "")
        return {
            "video_id": video_id,
            "title": title,
            "video_url": _build_video_url(video_id, title=title, duration_sec=duration_sec),
            "published_at": published_at,
            "privacy_status": str(status_obj.get("privacyStatus") or "public"),
            "duration_sec": duration_sec,
            "views": int(stats.get("viewCount", 0) or 0),
            "likes": int(stats.get("likeCount", 0) or 0),
            "comments": int(stats.get("commentCount", 0) or 0),
            "genre": "",
            "has_live_stats": True,
            "source": "YouTube Data API",
        }

    video_id = str(entry.get("video_id", "")).strip()
    title = str(entry.get("title") or "Untitled Video").strip()
    published_at = str(entry.get("published_at") or entry.get("created_at") or "")
    video_url = str(entry.get("video_url") or entry.get("url") or _build_video_url(video_id, title=title)).strip()
    if not (video_id or video_url or entry.get("video_path")):
        return None

    return {
        "video_id": video_id,
        "title": title,
        "video_url": video_url,
        "video_path": str(entry.get("video_path") or ""),
        "published_at": published_at,
        "privacy_status": str(entry.get("privacy_status") or entry.get("privacy") or "public"),
        "duration_sec": int(entry.get("duration_sec") or 0),
        "views": entry.get("views"),
        "likes": entry.get("likes"),
        "comments": entry.get("comments"),
        "genre": str(entry.get("genre") or ""),
        "has_live_stats": False,
        "source": "Local Studio Archive",
    }


def _load_local_published_videos() -> List[Dict[str, Any]]:
    """Loads locally archived and active PUBLISHED videos from JSON state."""
    from . import uploader

    files = [
        getattr(uploader, "ARCHIVE_FILE", ARCHIVE_FILE),
        getattr(uploader, "QUEUE_FILE", QUEUE_FILE),
    ]
    records: List[Dict[str, Any]] = []
    for path in files:
        if not path or not Path(path).exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and str(item.get("status", "")).upper() == "PUBLISHED":
                        norm = _normalize_video_entry(item, from_api=False)
                        if norm:
                            records.append(norm)
        except Exception:
            continue
    return records


def _fetch_recent_api_videos(
    limit: int,
    channel_id: Optional[str] = None,
    extra_video_ids: Optional[List[str]] = None,
) -> Tuple[bool, str, List[Dict[str, Any]], str]:
    """Queries YouTube Data API v3 for the channel's most recent uploaded videos."""
    extra_ids = [vid.strip() for vid in (extra_video_ids or []) if vid and str(vid).strip()]
    max_playlist_results = max(limit * 3, 10)

    for auth in _iter_youtube_auth_modes(channel_id=channel_id):
        ch_url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails,snippet&{auth['channel_query']}"
        try:
            ch_resp = requests.get(ch_url, headers=auth["headers"], timeout=15)
            if ch_resp.status_code != 200:
                continue
            ch_items = ch_resp.json().get("items", [])
            if not ch_items:
                continue

            ch = ch_items[0]
            channel_title = ch.get("snippet", {}).get("title", "Project Z Studio")
            uploads_playlist_id = (
                ch.get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads", "")
            )

            playlist_ids: List[str] = []
            if uploads_playlist_id:
                pl_url = (
                    "https://www.googleapis.com/youtube/v3/playlistItems"
                    f"?part=snippet,contentDetails&playlistId={uploads_playlist_id}"
                    f"&maxResults={max_playlist_results}{auth['key_param']}"
                )
                pl_resp = requests.get(pl_url, headers=auth["headers"], timeout=15)
                if pl_resp.status_code == 200:
                    for item in pl_resp.json().get("items", []):
                        vid = (
                            item.get("contentDetails", {}).get("videoId")
                            or item.get("snippet", {}).get("resourceId", {}).get("videoId")
                            or ""
                        ).strip()
                        if vid and vid not in playlist_ids:
                            playlist_ids.append(vid)

            # Query just-uploaded video IDs directly in case uploads playlist indexing lags by a few seconds.
            candidate_ids: List[str] = []
            for vid in extra_ids + playlist_ids:
                if vid and vid not in candidate_ids:
                    candidate_ids.append(vid)

            videos: List[Dict[str, Any]] = []
            if candidate_ids:
                ids_param = ",".join(candidate_ids[:25])
                vid_url = (
                    "https://www.googleapis.com/youtube/v3/videos"
                    f"?part=snippet,statistics,status,contentDetails&id={ids_param}{auth['key_param']}"
                )
                vid_resp = requests.get(vid_url, headers=auth["headers"], timeout=15)
                if vid_resp.status_code == 200:
                    for item in vid_resp.json().get("items", []):
                        norm = _normalize_video_entry(item, from_api=True)
                        if norm:
                            videos.append(norm)

            return True, channel_title, videos, auth["source"]
        except Exception as e:
            print(f"[YouTube Analytics] Recent videos API error ({auth['source']}): {e}")

    return False, "Project Z AI Studio (Local Archive)", [], "Local Studio Archive"


def get_recent_published_videos(
    limit: int = 3,
    channel_id: Optional[str] = None,
    extra_videos: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Returns the latest published YouTube videos (default last 3), preferring live
    YouTube Data API v3 stats and falling back gracefully to local archive records.
    """
    safe_limit = max(1, min(int(limit or 3), 25))
    normalized_extras: List[Dict[str, Any]] = []
    extra_ids: List[str] = []
    for raw in extra_videos or []:
        norm = _normalize_video_entry(raw, from_api=False)
        if norm:
            norm["_extra_priority"] = 1
            normalized_extras.append(norm)
            if norm.get("video_id"):
                extra_ids.append(norm["video_id"])

    connected, channel_title, api_videos, source_label = _fetch_recent_api_videos(
        limit=safe_limit,
        channel_id=channel_id,
        extra_video_ids=extra_ids,
    )

    merged: Dict[str, Dict[str, Any]] = {}

    def _dedup_key(v: Dict[str, Any]) -> str:
        if v.get("video_id"):
            return f"id:{v['video_id']}"
        return f"local:{v.get('video_path') or v.get('title')}"

    base_videos = api_videos if connected else _load_local_published_videos()
    for v in base_videos:
        merged[_dedup_key(v)] = dict(v)

    for extra in normalized_extras:
        key = _dedup_key(extra)
        if key in merged:
            if extra.get("genre") and not merged[key].get("genre"):
                merged[key]["genre"] = extra["genre"]
            merged[key]["_extra_priority"] = max(merged[key].get("_extra_priority", 0), 1)
        else:
            merged[key] = dict(extra)

    ordered = sorted(
        merged.values(),
        key=lambda v: (_parse_timestamp_sort_key(v.get("published_at", "")), v.get("_extra_priority", 0)),
        reverse=True,
    )
    selected = []
    for item in ordered[:safe_limit]:
        cleaned = dict(item)
        cleaned.pop("_extra_priority", None)
        cleaned.pop("video_path", None)
        selected.append(cleaned)

    return {
        "connected": connected,
        "channel_title": channel_title,
        "source": source_label,
        "count": len(selected),
        "limit": safe_limit,
        "videos": selected,
    }


def format_recent_videos_report(
    report_data: Optional[Dict[str, Any]] = None,
    limit: int = 3,
    just_uploaded_id: Optional[str] = None,
    html_mode: bool = False,
) -> str:
    """Formats the last N published YouTube videos in Markdown or Telegram HTML."""
    if report_data is None:
        report_data = get_recent_published_videos(limit=limit)

    videos = report_data.get("videos", [])
    channel_title = report_data.get("channel_title") or "YouTube Studio"
    connected = bool(report_data.get("connected"))
    requested = int(report_data.get("limit") or limit or 3)

    esc = (lambda s: html.escape(str(s), quote=True)) if html_mode else (lambda s: str(s))
    bold = (lambda s: f"<b>{esc(s)}</b>") if html_mode else (lambda s: f"**{s}**")
    link = (lambda u: f'<a href="{esc(u)}">{esc(u)}</a>') if html_mode else (lambda u: str(u))

    header_title = (
        f"🎬 Upload Complete — Last {requested} Published YouTube Videos"
        if just_uploaded_id
        else f"📺 Last {requested} Published YouTube Videos"
    )
    status_badge = "🟢 Live via YouTube Data API" if connected else "🟡 Local Studio Archive"
    lines = [
        bold(header_title),
        f"Channel: {esc(channel_title)} ({status_badge})",
    ]

    if not videos:
        lines.append("")
        lines.append("No published YouTube videos found yet.")
        return "\n".join(lines)

    privacy_labels = {"public": "🌐 Public", "unlisted": "🔗 Unlisted", "private": "🔒 Private"}

    for idx, vid in enumerate(videos, start=1):
        title = str(vid.get("title") or "Untitled Video")
        is_new = bool(just_uploaded_id and vid.get("video_id") == just_uploaded_id)
        prefix = f"{idx}. 🆕 JUST PUBLISHED — " if is_new else f"{idx}. "
        pub_str = _format_published_timestamp(vid.get("published_at", ""))
        privacy = privacy_labels.get(str(vid.get("privacy_status", "public")).lower(), "🌐 Public")
        dur_label = _format_duration_label(int(vid.get("duration_sec") or 0))
        meta_parts = [f"🕒 {esc(pub_str)}", privacy]
        if dur_label:
            meta_parts.append(f"⏱️ {esc(dur_label)}")

        lines.append("")
        lines.append(f"{bold(prefix + title)}")
        lines.append(" • ".join(meta_parts))

        if vid.get("has_live_stats"):
            views = int(vid.get("views") or 0)
            likes = int(vid.get("likes") or 0)
            comments = int(vid.get("comments") or 0)
            lines.append(f"👁️ {views:,} views • 👍 {likes:,} likes • 💬 {comments:,} comments")
        else:
            lines.append("📁 Recorded locally (live channel metrics sync when online)")

        v_url = str(vid.get("video_url") or "")
        if v_url:
            lines.append(f"🔗 {link(v_url)}")

    return "\n".join(lines)


def send_recent_videos_telegram_report(
    limit: int = 3,
    just_uploaded: Optional[Dict[str, Any]] = None,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """Builds the last-N published YouTube videos report and dispatches it to Telegram."""
    extra_videos = [just_uploaded] if just_uploaded else None
    just_uploaded_id = (just_uploaded or {}).get("video_id") or None
    report_data = get_recent_published_videos(limit=limit, extra_videos=extra_videos)
    report_markdown = format_recent_videos_report(
        report_data,
        limit=limit,
        just_uploaded_id=just_uploaded_id,
        html_mode=False,
    )
    report_html = format_recent_videos_report(
        report_data,
        limit=limit,
        just_uploaded_id=just_uploaded_id,
        html_mode=True,
    )

    sent = False
    try:
        import telegram_bridge

        sent = bool(
            telegram_bridge.send_telegram_alert(
                report_html,
                parse_mode="HTML",
                force=force,
            )
        )
    except Exception as e:
        print(f"[YouTube Analytics] Telegram report dispatch error: {e}")

    return {
        "sent": sent,
        "report": report_data,
        "message": report_markdown,
        "telegram_html": report_html,
    }
