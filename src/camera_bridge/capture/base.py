"""Capture backend interface: pull one still JPEG frame from a camera."""

from __future__ import annotations

from abc import ABC, abstractmethod


class CaptureError(Exception):
    """Raised when a camera cannot currently be captured from."""


class CaptureBackend(ABC):
    @abstractmethod
    def get_snapshot(self) -> bytes:
        """Return a single JPEG frame's bytes, or raise CaptureError."""
