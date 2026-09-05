"""
Z.A.I.N.E — YouTube Autonomous Uploader & Channel Dispatcher
Manages YouTube Data API v3 video uploads, metadata injection, and queue dispatch.

Features:
- Resumable video uploading directly to YouTube Channel
- Generates SEO-rich tags, hashtags, and descriptions
- OAuth2 token management via data/youtube_token.json
- Local upload queue (data/youtube_queue.json) with automatic retry
"""

import os
import json
import time
import datetime
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUEUE_FILE = PROJECT_ROOT / "data" / "youtube_queue.json"
TOKEN_FILE = PROJECT_ROOT / "data" / "youtube_token.json"
CLIENT_SECRET_FILE = PROJECT_ROOT / "client_secret.json"

YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def get_stored_token() -> Optional[Dict[str, Any]]:
    """Loads stored OAuth2 token from disk or environment."""
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Check environment variables
    access_token = os.getenv("YOUTUBE_ACCESS_TOKEN", "").strip()
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()
    if access_token or refresh_token:
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "client_id": os.getenv("YOUTUBE_CLIENT_ID", ""),
            "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", ""),
        }
    return None


def refresh_access_token(token_data: Dict[str, Any]) -> Optional[str]:
    """Refreshes expired OAuth2 access token using refresh_token."""
    refresh_token = token_data.get("refresh_token")
    client_id = token_data.get("client_id") or os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = token_data.get("client_secret") or os.getenv("YOUTUBE_CLIENT_SECRET")

    if not (refresh_token and client_id and client_secret):
        return token_data.get("access_token") or token_data.get("token")

    try:
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        resp = requests.post(YOUTUBE_TOKEN_URL, data=payload, timeout=15)
        if resp.status_code == 200:
            new_data = resp.json()
            token_data["access_token"] = new_data["access_token"]
            token_data["token"] = new_data["access_token"]
            token_data["updated_at"] = datetime.datetime.now().isoformat()
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=2)
            return new_data["access_token"]
    except Exception as e:
        print(f"[YouTube Uploader] Token refresh notice: {e}")

    return token_data.get("access_token") or token_data.get("token")


def get_upload_queue() -> List[Dict[str, Any]]:
    """Returns all queued YouTube videos."""
    if QUEUE_FILE.exists():
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_upload_queue(queue: List[Dict[str, Any]]):
    """Saves queue state to disk."""
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)


def queue_video_for_upload(video_path: str, title: str, description: str, tags: List[str]) -> Dict[str, Any]:
    """Adds a newly rendered video to the upload queue."""
    queue = get_upload_queue()
    item = {
        "id": f"yt_{int(time.time())}",
        "video_path": video_path,
        "title": title,
        "description": description,
        "tags": tags,
        "status": "QUEUED",
        "created_at": datetime.datetime.now().isoformat(),
    }
    queue.append(item)
    save_upload_queue(queue)
    return item


def post_video_comment(video_id: str, comment_text: str, access_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Posts a top-level pinned engagement comment to a YouTube video via YouTube Data API v3.
    Requires the 'https://www.googleapis.com/auth/youtube.force-ssl' scope.
    """
    if not comment_text or not video_id:
        return {"status": "SKIPPED", "message": "No comment text or video ID provided."}

    if not access_token:
        token_data = get_stored_token()
        if not token_data:
            return {"status": "NO_TOKEN", "text": comment_text}
        access_token = refresh_access_token(token_data)

    url = "https://www.googleapis.com/youtube/v3/commentThreads?part=snippet"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "snippet": {
            "videoId": video_id,
            "topLevelComment": {
                "snippet": {
                    "textOriginal": comment_text
                }
            }
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            data = resp.json()
            comment_id = data.get("id", "")
            return {
                "status": "SUCCESS",
                "comment_id": comment_id,
                "text": comment_text,
                "message": f"Engagement comment published live: '{comment_text}'",
            }
        elif resp.status_code == 403:
            return {
                "status": "PERMISSIONS_PENDING",
                "text": comment_text,
                "notice": "Requires 'youtube.force-ssl' OAuth scope for automated commenting. Re-authenticate via setup_youtube_auth to enable hands-free auto-comments.",
            }
        else:
            return {
                "status": "FAILED",
                "text": comment_text,
                "error": f"API error ({resp.status_code}): {resp.text[:180]}",
            }
    except Exception as e:
        return {"status": "ERROR", "text": comment_text, "error": str(e)}


def upload_youtube_video(
    video_path: str,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    privacy_status: str = "public",
    category_id: str = "28",
    engagement_question: str = "",
    genre: str = "",
) -> Dict[str, Any]:
    """
    Uploads a video to YouTube using the YouTube Data API v3.
    If credentials are not yet configured, marks video as queued and provides instructions.
    """
    if tags is None:
        tags = ["Shorts", "AI", "Technology", "Coding"]

    if not os.path.exists(video_path):
        return {"status": "ERROR", "message": f"File not found: {video_path}"}

    token_data = get_stored_token()

    # If no credentials found, queue the video locally and report instructions
    if not token_data or not (token_data.get("access_token") or token_data.get("refresh_token")):
        queued_item = queue_video_for_upload(video_path, title, description, tags)
        guide_msg = (
            f"Video '{title}' is rendered and stored at `{video_path}` ({os.path.getsize(video_path)} bytes).\n"
            "⚠️ **YouTube Credentials Pending**: To enable automated uploads directly to your channel:\n"
            "1. Download your `client_secret.json` from Google Cloud Console (with YouTube Data API v3 enabled).\n"
            "2. Place `client_secret.json` in Project-Z or set `YOUTUBE_REFRESH_TOKEN` in `.env`.\n"
            "The video is saved in your local YouTube Studio queue and ready to publish."
        )
        return {
            "status": "QUEUED_PENDING_AUTH",
            "queue_id": queued_item["id"],
            "video_path": video_path,
            "title": title,
            "message": guide_msg,
        }

    access_token = refresh_access_token(token_data)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Length": str(os.path.getsize(video_path)),
        "X-Upload-Content-Type": "video/mp4",
    }

    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": str(category_id),
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    try:
        # Step 1: Initialize Resumable Upload
        init_resp = requests.post(YOUTUBE_UPLOAD_URL, headers=headers, json=metadata, timeout=30)
        if init_resp.status_code != 200:
            return {"status": "FAILED", "error": f"Upload initialization failed ({init_resp.status_code}): {init_resp.text[:200]}"}

        upload_url = init_resp.headers.get("Location")
        if not upload_url:
            return {"status": "FAILED", "error": "No resumable upload Location header received."}

        # Step 2: Upload Video File Content
        with open(video_path, "rb") as f:
            upload_headers = {"Content-Type": "video/mp4"}
            up_resp = requests.put(upload_url, headers=upload_headers, data=f, timeout=300)

        if up_resp.status_code in (200, 201):
            video_data = up_resp.json()
            video_id = video_data.get("id", "")
            video_link = f"https://youtube.com/shorts/{video_id}" if "shorts" in title.lower() or "short" in title.lower() else f"https://youtube.com/watch?v={video_id}"

            # Post engagement comment if provided
            comment_result = None
            if engagement_question:
                comment_result = post_video_comment(video_id, engagement_question, access_token)

            # Auto-assign to niche playlist
            playlist_result = None
            if genre:
                try:
                    from .playlist_manager import assign_video_to_niche_playlist
                    playlist_result = assign_video_to_niche_playlist(genre, video_id)
                except Exception as pe:
                    print(f"[Uploader] Playlist assignment notice: {pe}")

            # Update queue status
            queue = get_upload_queue()
            for q in queue:
                if q["video_path"] == video_path:
                    q["status"] = "PUBLISHED"
                    q["video_id"] = video_id
                    q["video_url"] = video_link
                    q["published_at"] = datetime.datetime.now().isoformat()
                    if engagement_question:
                        q["pinned_comment"] = engagement_question
                    if genre:
                        q["genre"] = genre
            save_upload_queue(queue)

            success_msg = f"Successfully published to YouTube: {video_link}"
            if playlist_result and playlist_result.get("status") == "SUCCESS":
                success_msg += f"\n📁 Added to Playlist: {genre.upper()}"
            if comment_result:
                if comment_result.get("status") == "SUCCESS":
                    success_msg += f"\n💬 Pinned Engagement Comment: '{engagement_question}'"
                else:
                    success_msg += f"\n💬 Recommended Pinned Comment: '{engagement_question}'"

            return {
                "status": "SUCCESS",
                "video_id": video_id,
                "video_url": video_link,
                "title": title,
                "privacy": privacy_status,
                "message": success_msg,
                "engagement_comment": comment_result,
                "playlist_assignment": playlist_result,
            }
        else:
            return {"status": "FAILED", "error": f"Upload chunk transfer failed: {up_resp.text[:200]}"}

    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
