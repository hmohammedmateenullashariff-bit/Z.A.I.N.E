"""
Z.A.I.N.E — YouTube Studio & Higgsfield AI Authentication Setup
Assists in configuring:
1. Higgsfield AI API Keys (HIGGSFIELD_API_KEY_ID, HIGGSFIELD_API_SECRET)
2. YouTube Data API v3 OAuth2 credentials (client_secret.json / YOUTUBE_REFRESH_TOKEN)
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_FILE = DATA_DIR / "youtube_token.json"
CLIENT_SECRET_FILE = PROJECT_ROOT / "client_secret.json"

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def update_env_variable(key: str, value: str):
    """Safely adds or updates a key-value pair in .env."""
    lines = []
    found = False
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def setup_higgsfield_auth(key_id: str, secret: str) -> Dict[str, Any]:
    """Saves Higgsfield AI API credentials to .env."""
    key_id = key_id.strip()
    secret = secret.strip()
    if not key_id or not secret:
        return {"status": "error", "message": "Key ID and Secret cannot be empty."}

    update_env_variable("HIGGSFIELD_API_KEY_ID", key_id)
    update_env_variable("HIGGSFIELD_API_SECRET", secret)
    os.environ["HIGGSFIELD_API_KEY_ID"] = key_id
    os.environ["HIGGSFIELD_API_SECRET"] = secret

    return {
        "status": "success",
        "message": "Higgsfield AI credentials saved successfully to .env.",
        "key_id_preview": f"{key_id[:6]}...{key_id[-4:]}" if len(key_id) > 10 else key_id,
    }


def setup_youtube_oauth_from_file(secret_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes Google OAuth2 browser consent flow using client_secret.json.
    Saves refresh and access tokens to data/youtube_token.json and .env.
    """
    target_path = Path(secret_path) if secret_path else CLIENT_SECRET_FILE
    if not target_path.exists():
        alt_path = DATA_DIR / "client_secret.json"
        if alt_path.exists():
            target_path = alt_path

    if not target_path.exists():
        return {
            "status": "missing_client_secret",
            "message": (
                f"client_secret.json not found at {target_path}.\n"
                "Please download your OAuth 2.0 Client ID (Desktop App) JSON from Google Cloud Console:\n"
                "https://console.cloud.google.com/apis/credentials\n"
                f"and save it as: {CLIENT_SECRET_FILE}"
            ),
        }

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        print(f"[YouTube Auth] Found client secret at: {target_path}")
        print("[YouTube Auth] Launching browser consent flow on localhost port 8090...")

        flow = InstalledAppFlow.from_client_secrets_file(str(target_path), scopes=YOUTUBE_SCOPES)
        creds = flow.run_local_server(port=8090, prompt="consent", access_type="offline")

        token_data = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
        }

        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)

        if creds.refresh_token:
            update_env_variable("YOUTUBE_REFRESH_TOKEN", creds.refresh_token)
            update_env_variable("YOUTUBE_CLIENT_ID", creds.client_id)
            update_env_variable("YOUTUBE_CLIENT_SECRET", creds.client_secret)

        print("[YouTube Auth] Authentication successful! Tokens stored in data/youtube_token.json")
        return {
            "status": "success",
            "message": "YouTube OAuth2 authentication complete and tokens stored.",
            "token_file": str(TOKEN_FILE),
        }
    except Exception as e:
        return {"status": "error", "message": f"OAuth authorization flow failed: {e}"}


def setup_youtube_manual_credentials(client_id: str, client_secret: str, refresh_token: str) -> Dict[str, Any]:
    """Manually saves YouTube OAuth credentials to .env and data/youtube_token.json."""
    update_env_variable("YOUTUBE_CLIENT_ID", client_id.strip())
    update_env_variable("YOUTUBE_CLIENT_SECRET", client_secret.strip())
    update_env_variable("YOUTUBE_REFRESH_TOKEN", refresh_token.strip())

    token_data = {
        "client_id": client_id.strip(),
        "client_secret": client_secret.strip(),
        "refresh_token": refresh_token.strip(),
    }
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

    return {"status": "success", "message": "Manual YouTube credentials saved."}
