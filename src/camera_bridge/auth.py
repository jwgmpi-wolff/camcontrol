"""Simple username/password auth: PBKDF2-hashed users persisted to a local
JSON file, plus short-lived opaque bearer tokens issued on login. No external
IdP (e.g. Entra ID) — this is intentionally a self-contained user store for
the gateway's own Android/iOS/desktop clients.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path

from .blob_config_sync import download_if_configured, upload_if_configured

_PBKDF2_ITERATIONS = 200_000
_TOKEN_TTL_SECONDS = 24 * 60 * 60

DEFAULT_USERS_PATH = Path("config/users.json")


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations_str, salt_hex, digest_hex = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(actual, expected)


class UserStore:
    """Persists {username: password_hash} to a local JSON file."""

    def __init__(self, path: Path = DEFAULT_USERS_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._users: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        download_if_configured(self._path)
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._users, indent=2), encoding="utf-8")
        upload_if_configured(self._path)

    def is_empty(self) -> bool:
        with self._lock:
            return not self._users

    def add_user(self, username: str, password: str) -> None:
        if not username or not password:
            raise ValueError("username and password are required")
        with self._lock:
            self._users[username] = hash_password(password)
            self._save()

    def remove_user(self, username: str) -> bool:
        with self._lock:
            existed = self._users.pop(username, None) is not None
            if existed:
                self._save()
            return existed

    def verify(self, username: str, password: str) -> bool:
        with self._lock:
            stored = self._users.get(username)
        if stored is None:
            return False
        return verify_password(password, stored)

    def list_usernames(self) -> list[str]:
        with self._lock:
            return sorted(self._users)


class TokenManager:
    """In-memory opaque bearer tokens with a fixed TTL. Tokens don't survive
    a gateway restart by design — clients re-authenticate with their stored
    username/password, which is fine for this trusted-LAN/self-hosted use."""

    def __init__(self, ttl_seconds: float = _TOKEN_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._tokens: dict[str, tuple[str, float]] = {}

    def issue(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._tokens[token] = (username, time.monotonic() + self._ttl)
        return token

    def validate(self, token: str) -> str | None:
        with self._lock:
            entry = self._tokens.get(token)
            if entry is None:
                return None
            username, expires_at = entry
            if time.monotonic() >= expires_at:
                del self._tokens[token]
                return None
            return username

    def revoke(self, token: str) -> None:
        with self._lock:
            self._tokens.pop(token, None)
