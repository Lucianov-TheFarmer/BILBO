"""Short-lived Google Drive grants and FASTQ name normalization."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path

import redis
import requests
from cryptography.fernet import Fernet

from ..core.settings import settings


DRIVE_API = "https://www.googleapis.com/drive/v3/files"
SESSION_TTL = 72 * 3600
_PAIR = re.compile(r"^(?P<base>.+)_R(?P<mate>[12])(?:_001)?\.(?:fastq|fq)\.gz$", re.I)
_SIMPLE = re.compile(r"^(?P<base>.+)_(?P<mate>[12])\.(?:fastq|fq)\.gz$", re.I)


def parse_fastq_pair(filename: str) -> tuple[str, int]:
    """Reject unknown naming patterns rather than silently mispairing reads."""
    if Path(filename).name != filename or any(c in filename for c in ("/", "\\", "\x00")):
        raise ValueError("Invalid FASTQ filename")
    match = _PAIR.fullmatch(filename) or _SIMPLE.fullmatch(filename)
    if not match:
        raise ValueError("FASTQ filename does not identify R1 or R2")
    base = match.group("base")
    # Preserve sample index and lane in the key to avoid accidental collisions.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}", base):
        raise ValueError("Invalid sample name")
    return base, int(match.group("mate"))


def redis_client():
    return redis.Redis.from_url(settings.celery_broker_url, decode_responses=True)


def session_key(session_id: str) -> str:
    return f"bilbo:drive:session:{session_id}"


def state_key(state: str) -> str:
    return f"bilbo:drive:state:{state}"


def _cipher():
    if settings.secret_key == "change-me-in-production":
        raise RuntimeError("Set SECRET_KEY before enabling Google Drive")
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def save_credentials(session_id: str, credentials: dict):
    if not credentials.get("refresh_token"):
        raise ValueError("Google did not provide an offline access grant")
    credentials["expires_at"] = time.time() + int(credentials.get("expires_in", 3600))
    encrypted = _cipher().encrypt(json.dumps(credentials).encode()).decode()
    r = redis_client()
    r.hset(session_key(session_id), "credentials", encrypted)
    r.expire(session_key(session_id), SESSION_TTL)


def access_token(session_id: str) -> str:
    r = redis_client()
    raw = r.hget(session_key(session_id), "credentials")
    if not raw:
        raise ValueError("Google Drive connection expired")
    credentials = json.loads(_cipher().decrypt(raw.encode()))
    if time.time() < float(credentials.get("expires_at", 0)) - 60:
        return credentials["access_token"]
    if credentials.get("refresh_token"):
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": os.environ["GOOGLE_DRIVE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_DRIVE_CLIENT_SECRET"],
                "refresh_token": credentials["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        response.raise_for_status()
        refreshed = response.json()
        credentials["access_token"] = refreshed["access_token"]
        credentials["expires_in"] = refreshed.get("expires_in", 3600)
        save_credentials(session_id, credentials)
        return credentials["access_token"]
    raise ValueError("Google Drive connection expired")


def file_metadata(session_id: str, file_id: str) -> dict:
    response = requests.get(
        f"{DRIVE_API}/{file_id}",
        headers={"Authorization": f"Bearer {access_token(session_id)}"},
        params={"fields": "id,name,mimeType,size,md5Checksum,capabilities(canDownload)"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("capabilities", {}).get("canDownload", False):
        raise ValueError("Download is not permitted for this file")
    return data
