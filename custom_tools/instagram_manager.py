import os
import json
from pathlib import Path

SESSION_FILE = Path(__file__).parent.parent / "data" / "instagram_session.json"
SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

def instagram_manager(action: str = "stats", username: str = "", password: str = "", video_path: str = "", caption: str = "") -> str:
    """
    Autonomous Instagram Operations Suite via instagrapi:
    - 'stats': Fetches profile stats and follower count for any public handle.
    - 'publish_reel': Uploads an MP4 video as an Instagram Reel with caption and hashtags.
    - 'status': Checks Instagram client readiness and session state.
    """
    act = action.strip().lower()
    
    if act == "stats":
        target_user = username.strip() or os.getenv("INSTAGRAM_USERNAME", "mateen")
        try:
            from instagrapi import Client
            cl = Client()
            user_info = cl.user_info_by_username(target_user)
            return (
                f"Instagram Profile for @{target_user}:\n"
                f"- Full Name: {user_info.full_name}\n"
                f"- Followers: {user_info.follower_count:,}\n"
                f"- Following: {user_info.following_count:,}\n"
                f"- Total Posts: {user_info.media_count}\n"
                f"- Bio: {user_info.biography[:120]}"
            )
        except Exception as e:
            return f"Instagram stats query note: {e}"
            
    elif act == "publish_reel":
        if not video_path:
            return "Error: No video_path specified for Reel upload."
        vpath = Path(video_path)
        if not vpath.exists():
            return f"Error: Video file '{video_path}' does not exist."
            
        u = username.strip() or os.getenv("INSTAGRAM_USERNAME", "")
        p = password.strip() or os.getenv("INSTAGRAM_PASSWORD", "")
        if not u or not p:
            return "Instagram credentials not set. Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in .env or pass them directly."
            
        try:
            from instagrapi import Client
            cl = Client()
            if SESSION_FILE.exists():
                try:
                    cl.load_settings(SESSION_FILE)
                except Exception:
                    pass
            cl.login(u, p)
            cl.dump_settings(SESSION_FILE)
            
            media = cl.clip_upload(
                path=str(vpath),
                caption=caption or "Created autonomously with Z.A.I.N.E AI"
            )
            return f"Success: Instagram Reel published! Media ID: {media.id}, Code: {media.code}"
        except Exception as e:
            return f"Instagram Reel upload error: {e}"
            
    else:
        # Default: status
        return f"Instagram Suite Ready. Library instagrapi active. Session cache: {'Present' if SESSION_FILE.exists() else 'None'}."
