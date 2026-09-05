"""
Z.A.I.N.E — YouTube Autonomous Analytics & Channel Growth Tracker
Queries channel metrics, tracks 24-hour subscriber/view deltas,
and generates formatted executive growth dossiers for Telegram and voice.
"""

import os
import json
import datetime
import requests
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYTICS_HISTORY = PROJECT_ROOT / "data" / "youtube_analytics_history.json"
QUEUE_FILE = PROJECT_ROOT / "data" / "youtube_queue.json"


def get_channel_analytics(channel_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches real-time channel statistics via YouTube Data API v3.
    Falls back to local studio metrics if API credentials are not yet linked.
    """
    from .uploader import get_stored_token, refresh_access_token

    token_data = get_stored_token()
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()

    # 1. Try Authenticated Channel Request
    if token_data and (token_data.get("access_token") or token_data.get("token") or token_data.get("refresh_token")):
        access_token = refresh_access_token(token_data) or token_data.get("token")
        headers = {"Authorization": f"Bearer {access_token}"}
        url = "https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet&mine=true"
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
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
                        "source": "YouTube Data API (OAuth2)",
                    })
                else:
                    return _record_analytics_snapshot({
                        "connected": True,
                        "channel_title": "Authenticated Google Account",
                        "custom_url": "",
                        "subscribers": 0,
                        "total_views": 0,
                        "total_videos": 0,
                        "notice": "Google OAuth is active! If your channel has not been initialized yet, visit https://www.youtube.com/create_channel to set your channel name.",
                        "source": "YouTube Data API (OAuth2)",
                    })
        except Exception as e:
            print(f"[YouTube Analytics] OAuth request error: {e}")

    # 2. Try Public API Key with Channel ID
    if api_key and channel_id:
        url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet&id={channel_id}&key={api_key}"
        try:
            resp = requests.get(url, timeout=15)
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
                        "source": "YouTube Data API (Key)",
                    })
        except Exception as e:
            print(f"[YouTube Analytics] Public API error: {e}")

    # 3. Fallback: Local Studio Production Statistics
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
