"""Local-filesystem storage backend."""

from __future__ import annotations

from pathlib import Path

from ..models import LocalStorageConfig
from .base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, config: LocalStorageConfig) -> None:
        self._root = Path(config.path)

    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        dest = self._root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return str(dest)
