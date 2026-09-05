"""
Z.A.I.N.E — YouTube Autonomous Playlist Manager
Creates and organizes niche playlists on the channel:
- ⚔️ Anime Power Arena & Matchups
- 🎮 Epic Gaming Secrets & Lore
- 🧠 Mind-Blowing Facts & Wonders
- 🐾 Hilarious Feline Chaos & Cat Memes
- 👶 Family & Toddler Comedy
- ⚡ Frontier AI & Tech Intelligence
- ✨ Whimsical Animated Cartoon Tales
"""

import json
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional
from .uploader import get_stored_token, refresh_access_token

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAYLIST_FILE = PROJECT_ROOT / "data" / "youtube_playlists.json"

PLAYLIST_DEFINITIONS = {
    "anime": {
        "title": "⚔️ Anime Power Arena & Battles",
        "description": "Epic anime power scaling debates, fight analyses, and theory breakdowns (Naruto, One Piece, Dragon Ball, JJK) by Zaine Studio.",
    },
    "gaming": {
        "title": "🎮 Epic Gaming Secrets & Lore",
        "description": "Deep-dive video game lore, hidden easter eggs, and next-gen physics breakdowns (Elden Ring, GTA 6, Soulsborne).",
    },
    "facts": {
        "title": "🧠 Mind-Blowing Facts & World Wonders",
        "description": "Mind-bending cosmic space secrets, psychological anomalies, and fascinating real-world curiosities.",
    },
    "cat": {
        "title": "🐾 Hilarious Feline Chaos & Cat Memes",
        "description": "Daily 3 AM zoomies, cat logic, and hilarious feline confessions curated by Zaine Studio.",
    },
    "kids": {
        "title": "👶 Family & Toddler Comedy",
        "description": "Wholesome, hilarious toddler excuses, bedtime negotiations, and parenting laughs.",
    },
    "tech": {
        "title": "⚡ Frontier AI & Systems Intelligence",
        "description": "Real-time AI model breakthroughs, distributed systems architecture, and engineering wisdom.",
    },
    "animated": {
        "title": "✨ Whimsical Animated Cartoon Tales",
        "description": "Original cartoon shorts, storybook animations, and delightful character adventures.",
    },
}


def load_cached_playlists() -> Dict[str, str]:
    """Loads cached playlist mapping {genre: playlist_id} from disk."""
    if PLAYLIST_FILE.exists():
        try:
            with open(PLAYLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cached_playlists(mapping: Dict[str, str]):
    """Saves playlist mapping to disk."""
    PLAYLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)


def fetch_channel_playlists(access_token: str) -> List[Dict[str, Any]]:
    """Fetches all existing playlists on the authenticated channel."""
    url = "https://www.googleapis.com/youtube/v3/playlists?part=snippet&mine=true&maxResults=50"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("items", [])
    except Exception as e:
        print(f"[Playlist Manager] Error fetching playlists: {e}")
    return []


def create_youtube_playlist(title: str, description: str, access_token: str) -> Optional[str]:
    """Creates a new playlist on YouTube and returns its playlistId."""
    url = "https://www.googleapis.com/youtube/v3/playlists?part=snippet,status"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "snippet": {
            "title": title,
            "description": description,
        },
        "status": {
            "privacyStatus": "public",
        },
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            data = resp.json()
            p_id = data.get("id")
            print(f"[Playlist Manager] Created playlist: '{title}' -> ID: {p_id}")
            return p_id
        else:
            print(f"[Playlist Manager] Failed to create playlist '{title}' ({resp.status_code}): {resp.text[:150]}")
    except Exception as e:
        print(f"[Playlist Manager] Exception creating playlist '{title}': {e}")
    return None


def add_video_to_playlist(playlist_id: str, video_id: str, access_token: str) -> bool:
    """Adds a video to a specific playlist via playlistItems.insert."""
    url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id,
            },
        },
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            print(f"[Playlist Manager] Successfully added video {video_id} to playlist {playlist_id}")
            return True
        else:
            print(f"[Playlist Manager] Notice adding to playlist ({resp.status_code}): {resp.text[:150]}")
    except Exception as e:
        print(f"[Playlist Manager] Exception adding to playlist: {e}")
    return False


def ensure_channel_playlists() -> Dict[str, Any]:
    """
    Ensures all 7 niche playlists exist on the YouTube channel.
    Caches playlist IDs in data/youtube_playlists.json.
    """
    token_data = get_stored_token()
    if not token_data:
        return {"status": "NO_AUTH", "message": "YouTube authentication credentials pending."}

    access_token = refresh_access_token(token_data)
    cached = load_cached_playlists()

    # Fetch existing playlists from channel to avoid duplicate creation
    existing_items = fetch_channel_playlists(access_token)
    existing_title_to_id = {item["snippet"]["title"].lower(): item["id"] for item in existing_items if "snippet" in item}

    updated = False
    for genre, p_def in PLAYLIST_DEFINITIONS.items():
        if genre in cached and cached[genre]:
            continue

        p_title = p_def["title"]
        # Check if already on channel
        if p_title.lower() in existing_title_to_id:
            cached[genre] = existing_title_to_id[p_title.lower()]
            updated = True
        else:
            new_id = create_youtube_playlist(p_title, p_def["description"], access_token)
            if new_id:
                cached[genre] = new_id
                updated = True

    if updated:
        save_cached_playlists(cached)

    return {
        "status": "SUCCESS",
        "playlists": cached,
        "count": len(cached),
    }


def assign_video_to_niche_playlist(genre: str, video_id: str) -> Dict[str, Any]:
    """
    Assigns an uploaded video to its corresponding niche playlist on YouTube.
    """
    if not video_id:
        return {"status": "SKIPPED", "message": "No video_id provided"}

    norm_genre = genre.lower().strip()
    cached = load_cached_playlists()

    token_data = get_stored_token()
    if not token_data:
        return {"status": "SKIPPED", "message": "No auth token"}

    access_token = refresh_access_token(token_data)

    playlist_id = cached.get(norm_genre)
    if not playlist_id:
        ensure_res = ensure_channel_playlists()
        cached = ensure_res.get("playlists", {})
        playlist_id = cached.get(norm_genre)

    if playlist_id:
        success = add_video_to_playlist(playlist_id, video_id, access_token)
        return {
            "status": "SUCCESS" if success else "FAILED",
            "playlist_id": playlist_id,
            "genre": norm_genre,
            "video_id": video_id,
        }

    return {"status": "NOT_FOUND", "message": f"No playlist found for genre '{norm_genre}'"}
