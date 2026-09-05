"""Storage backend interface: persist a captured JPEG somewhere durable."""

from __future__ import annotations

from abc import ABC, abstractmethod


class StorageError(Exception):
    """Raised when a capture cannot be persisted to the configured backend."""


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        """Persist data under key. Returns a human-readable location string."""
