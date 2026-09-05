"""WebDAV storage backend (e.g. Nextcloud, ownCloud, generic WebDAV server)."""

from __future__ import annotations

import httpx

from ..models import WebDavStorageConfig
from .base import StorageBackend, StorageError


class WebDavStorage(StorageBackend):
    def __init__(self, config: WebDavStorageConfig) -> None:
        self._config = config

    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        remote_dir = self._config.remote_dir.strip("/")
        url = f"{self._config.base_url.rstrip('/')}/{remote_dir}/{key}".rstrip("/")
        auth = None
        if self._config.username:
            auth = (self._config.username, self._config.password)
        try:
            response = httpx.put(
                url,
                content=data,
                headers={"Content-Type": content_type},
                auth=auth,
                timeout=15,
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"WebDAV PUT failed for {url}: {exc}") from exc
        return url
