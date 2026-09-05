"""Optional capability: browse and read files from a camera's local storage
(e.g. a mounted microSD card), in addition to pulling live snapshots.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from pydantic import BaseModel


class MediaFile(BaseModel):
    path: str
    size: int
    modified_epoch: int
    media_type: str  # "image" | "video" | "other"


def guess_media_type(path: str) -> str:
    lower = path.lower()
    if lower.endswith((".jpg", ".jpeg", ".png", ".bmp")):
        return "image"
    if lower.endswith((".mp4", ".avi", ".mkv", ".h264", ".ts")):
        return "video"
    return "other"


class MediaBrowser(ABC):
    @abstractmethod
    def list_media(self) -> list[MediaFile]:
        """List files under the camera's local media directory."""

    @abstractmethod
    def read_media(self, path: str) -> Iterator[bytes]:
        """Stream a file's bytes given a path previously returned by list_media."""
