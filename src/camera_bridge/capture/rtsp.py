"""Capture backend for cameras that expose a standard RTSP stream.

Uses a local ffmpeg binary to pull exactly one frame per snapshot request.
"""

from __future__ import annotations

import subprocess

from ..models import RtspCameraConfig
from .base import CaptureBackend, CaptureError


class RtspCapture(CaptureBackend):
    def __init__(self, config: RtspCameraConfig, ffmpeg_path: str = "ffmpeg") -> None:
        self._config = config
        self._ffmpeg_path = ffmpeg_path

    def get_snapshot(self) -> bytes:
        cmd = [
            self._ffmpeg_path,
            "-y",
            "-rtsp_transport",
            "tcp",
            "-i",
            self._config.rtsp_url,
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
            raise CaptureError(
                f"Timed out capturing from {self._config.rtsp_url}"
            ) from exc

        if not result.stdout:
            raise CaptureError(
                f"ffmpeg produced no frame for {self._config.rtsp_url}: "
                f"{result.stderr.decode(errors='replace')[-500:]}"
            )
        return result.stdout
