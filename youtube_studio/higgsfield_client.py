"""
Z.A.I.N.E — Higgsfield AI Video Generation Client
Connects to Higgsfield AI REST API (https://api.higgsfield.ai/) to generate
photorealistic, cinematic 9:16 vertical video footage for YouTube Shorts.

Features:
- Asynchronous job submission & polling
- Automatic clip downloading into workspace/youtube_shorts/broll/
- Graceful procedural cybernetic fallback if API credentials are not yet set in .env
"""

import os
import sys
import time
import json
import requests
from pathlib import Path
from typing import Optional, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BROLL_DIR = PROJECT_ROOT / "workspace" / "youtube_shorts" / "broll"
BROLL_DIR.mkdir(parents=True, exist_ok=True)

HIGGSFIELD_API_BASE = "https://api.higgsfield.ai"


def get_higgsfield_credentials() -> Dict[str, str]:
    """Retrieves Higgsfield API credentials from environment."""
    key_id = os.getenv("HIGGSFIELD_API_KEY_ID", "").strip()
    secret = os.getenv("HIGGSFIELD_API_SECRET", "").strip()
    return {"key_id": key_id, "secret": secret}


def has_higgsfield_credentials() -> bool:
    """Checks if valid Higgsfield credentials exist."""
    creds = get_higgsfield_credentials()
    return bool(creds["key_id"] and creds["secret"])


def generate_higgsfield_video(
    prompt: str,
    aspect_ratio: str = "9:16",
    duration_seconds: int = 5,
    timeout_seconds: int = 180,
) -> Optional[str]:
    """
    Submits a cinematic video generation job to Higgsfield AI,
    polls until complete, and downloads the output MP4 to workspace.
    Returns path to downloaded MP4, or None if fallback is needed.
    """
    creds = get_higgsfield_credentials()
    if not (creds["key_id"] and creds["secret"]):
        print("[Higgsfield AI] Credentials not found in .env. Using high-tech procedural visual engine.")
        return None

    headers = {
        "Authorization": f"Key {creds['key_id']}:{creds['secret']}",
        "Content-Type": "application/json",
        "User-Agent": "ZAINE-Autonomous-Studio/1.0",
    }

    # Format prompt with cinematic style tags
    cinematic_prompt = f"{prompt}, 8k resolution, cinematic lighting, hyper-realistic, photorealistic, 60fps, vertical {aspect_ratio}"

    payload = {
        "prompt": cinematic_prompt,
        "aspect_ratio": aspect_ratio,
        "duration": duration_seconds,
    }

    try:
        # 1. Submit Generation Request
        endpoint = f"{HIGGSFIELD_API_BASE}/higgsfield-ai/soul/v2/standard"
        print(f"[Higgsfield AI] Submitting video prompt: '{prompt[:60]}...'")
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=20)

        if resp.status_code not in (200, 201, 202):
            print(f"[Higgsfield AI] Request failed ({resp.status_code}): {resp.text[:150]}")
            return None

        job_data = resp.json()
        request_id = job_data.get("request_id") or job_data.get("id")
        status_url = job_data.get("status_url") or f"{HIGGSFIELD_API_BASE}/requests/{request_id}"

        if not request_id:
            print("[Higgsfield AI] No request_id returned in response.")
            return None

        print(f"[Higgsfield AI] Job queued. Request ID: {request_id}. Polling for completion...")

        # 2. Poll Status Asynchronously
        t_start = time.time()
        video_url = None

        while time.time() - t_start < timeout_seconds:
            time.sleep(6)
            poll_resp = requests.get(status_url, headers=headers, timeout=15)
            if poll_resp.status_code != 200:
                continue

            status_data = poll_resp.json()
            status = status_data.get("status", "").lower()

            if status in ("completed", "done", "succeeded"):
                video_url = status_data.get("video_url") or status_data.get("output", {}).get("url")
                print("[Higgsfield AI] Video rendering complete!")
                break
            elif status in ("failed", "error", "rejected"):
                print(f"[Higgsfield AI] Video generation failed: {status_data.get('error')}")
                return None
            else:
                elapsed = int(time.time() - t_start)
                print(f"  [Higgsfield AI Polling] Status: {status} ({elapsed}s elapsed)...")

        if not video_url:
            print("[Higgsfield AI] Polling timed out. Falling back to local visual engine.")
            return None

        # 3. Download the Rendered MP4
        timestamp = int(time.time())
        dest_filename = f"higgsfield_{timestamp}.mp4"
        dest_path = BROLL_DIR / dest_filename

        print(f"[Higgsfield AI] Downloading generated video from {video_url}...")
        vid_resp = requests.get(video_url, stream=True, timeout=30)
        with open(dest_path, "wb") as f:
            for chunk in vid_resp.iter_content(chunk_size=65536):
                f.write(chunk)

        print(f"[Higgsfield AI] Saved video to: {dest_path} ({os.path.getsize(dest_path)} bytes)")
        return str(dest_path)

    except Exception as e:
        print(f"[Higgsfield AI] Integration notice: {e}. Falling back to procedural engine.")
        return None
