"""Capture backend for cameras that expose a standard RTSP stream.

Uses a local ffmpeg binary to pull exactly one frame per snapshot request.
"""

from __future__ import annotations

import subprocess
from urllib.parse import quote, urlsplit, urlunsplit

from ..models import RtspCameraConfig
from .base import CaptureBackend, CaptureError


def _effective_url(config: RtspCameraConfig) -> str:
    """rtsp_url with username/password injected, unless it already has its
    own userinfo (e.g. "rtsp://user:pass@host/...") -- that takes priority."""
    if not config.username:
        return config.rtsp_url
    parts = urlsplit(config.rtsp_url)
    if "@" in parts.netloc:
        return config.rtsp_url
    userinfo = quote(config.username, safe="")
    if config.password:
        userinfo += f":{quote(config.password, safe='')}"
    return urlunsplit((parts.scheme, f"{userinfo}@{parts.netloc}", parts.path, parts.query, parts.fragment))


def _redacted_url(url: str) -> str:
    """Never let a userinfo section reach logs/error messages."""
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url
    return urlunsplit((parts.scheme, f"***@{parts.netloc.rsplit('@', 1)[1]}", parts.path, parts.query, parts.fragment))


class RtspCapture(CaptureBackend):
    def __init__(self, config: RtspCameraConfig, ffmpeg_path: str = "ffmpeg") -> None:
        self._config = config
        self._ffmpeg_path = ffmpeg_path

    def get_snapshot(self) -> bytes:
        url = _effective_url(self._config)
        display_url = _redacted_url(url)
        cmd = [
            self._ffmpeg_path,
            "-y",
            "-rtsp_transport",
            "tcp",
            "-i",
            url,
            "-frames:v",
            "1",
            "-f",
            "image2",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CaptureError(f"Timed out capturing from {display_url}") from exc

        if not result.stdout:
            raise CaptureError(
                f"ffmpeg produced no frame for {display_url}: "
                f"{result.stderr.decode(errors='replace')[-500:]}"
            )
        return result.stdout

