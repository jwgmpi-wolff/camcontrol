"""Build the correct capture backend for a given camera config."""

from __future__ import annotations

from ..models import CameraConfig, RtspCameraConfig, YiHackV3SshCameraConfig
from .base import CaptureBackend
from .rtsp import RtspCapture
from .yi_hack_v3_ssh import YiHackV3SshCapture


def build_capture_backend(config: CameraConfig) -> CaptureBackend:
    if isinstance(config, YiHackV3SshCameraConfig):
        return YiHackV3SshCapture(config)
    if isinstance(config, RtspCameraConfig):
        return RtspCapture(config)
    raise ValueError(f"Unsupported camera config type: {type(config)!r}")
