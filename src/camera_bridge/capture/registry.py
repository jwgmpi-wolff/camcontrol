"""Build the correct capture backend for a given camera config."""

from __future__ import annotations

from ..models import CameraConfig, Hi3518eSshCameraConfig, RtspCameraConfig
from .base import CaptureBackend
from .hi3518e_ssh import Hi3518eSshCapture
from .rtsp import RtspCapture


def build_capture_backend(config: CameraConfig) -> CaptureBackend:
    if isinstance(config, Hi3518eSshCameraConfig):
        return Hi3518eSshCapture(config)
    if isinstance(config, RtspCameraConfig):
        return RtspCapture(config)
    raise ValueError(f"Unsupported camera config type: {type(config)!r}")
