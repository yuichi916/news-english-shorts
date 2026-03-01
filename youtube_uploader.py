"""YouTube Shorts uploader — OAuth 2.0 + YouTube Data API v3."""

from __future__ import annotations

import os
import random
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ── Constants ─────────────────────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_FILE = os.path.join(PROJECT_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(PROJECT_DIR, "youtube_token.json")

MAX_RETRIES = 5


# ── Authentication ────────────────────────────────────────────────────────────

def has_client_secret() -> bool:
    """Return True if client_secret.json exists."""
    return os.path.isfile(CLIENT_SECRET_FILE)


def is_authenticated() -> bool:
    """Return True if a valid (or refreshable) token exists."""
    if not os.path.isfile(TOKEN_FILE):
        return False
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        return creds.valid or (creds.expired and creds.refresh_token is not None)
    except Exception:
        return False


def authenticate() -> Credentials:
    """Authenticate via OAuth 2.0 and return credentials.

    - If a saved token exists, load and refresh it.
    - Otherwise, launch a local browser flow.
    - Saves the token to *TOKEN_FILE* for future use.
    """
    creds: Credentials | None = None

    if os.path.isfile(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not has_client_secret():
            raise FileNotFoundError(
                f"client_secret.json が見つかりません: {CLIENT_SECRET_FILE}\n"
                "Google Cloud Console から OAuth 2.0 クライアントIDをダウンロードし、"
                "プロジェクトルートに配置してください。"
            )
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        creds = flow.run_local_server(port=0)

    # Save for next time
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    return creds


def logout() -> None:
    """Remove saved token file."""
    if os.path.isfile(TOKEN_FILE):
        os.remove(TOKEN_FILE)


# ── Upload ────────────────────────────────────────────────────────────────────

def upload_video(
    file_path: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    privacy: str = "private",
) -> str:
    """Upload a video to YouTube and return the video ID.

    Uses resumable upload with exponential backoff retry.
    """
    creds = authenticate()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": "27",  # Education
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    video_id = _resumable_upload(request)
    return video_id


def _resumable_upload(request) -> str:
    """Execute a resumable upload with exponential backoff."""
    response = None
    retry = 0

    while response is None:
        try:
            _, response = request.next_chunk()
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < MAX_RETRIES:
                retry += 1
                sleep_sec = 2 ** retry + random.random()
                time.sleep(sleep_sec)
            else:
                raise

    return response["id"]


# ── Metadata builder ──────────────────────────────────────────────────────────

def build_metadata(
    script_data: dict,
    description_text: str = "",
) -> dict:
    """Build title / description / tags from script JSON and description file.

    Returns ``{"title": ..., "description": ..., "tags": [...]}``.
    """
    topic = script_data.get("topic", "News English Short")
    title = f"{topic} #Shorts"
    # YouTube title max 100 chars
    if len(title) > 100:
        title = title[:97] + "..."

    tags = list(script_data.get("hashtags", []))
    if "#Shorts" not in tags and "Shorts" not in tags:
        tags.insert(0, "Shorts")

    return {
        "title": title,
        "description": description_text,
        "tags": tags,
    }
