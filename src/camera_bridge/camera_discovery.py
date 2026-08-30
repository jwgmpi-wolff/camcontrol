"""Standards-based USB/UVC camera discovery and capability probing."""

from __future__ import annotations

import glob
import logging
import platform
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CameraCapability:
    width: int
    height: int
    fps: float
    pixel_format: str = "unknown"


@dataclass(slots=True)
class CameraDevice:
    device_path: str
    name: str
    is_uvc_compatible: bool
    backend: str
    usb_metadata: dict[str, str] = field(default_factory=dict)
    capabilities: list[CameraCapability] = field(default_factory=list)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CameraDiscovery:
    def __init__(self, max_windows_indexes: int = 10) -> None:
        self.max_windows_indexes = max_windows_indexes

    def discover(self, requested_device: str | None = None) -> list[CameraDevice]:
        candidates = [requested_device] if requested_device else self._candidates()
        devices = [self.probe(candidate) for candidate in candidates if candidate]
        return [device for device in devices if device.is_uvc_compatible]

    def probe(self, device_path: str) -> CameraDevice:
        source = self._opencv_source(device_path)
        capture = cv2.VideoCapture(source, self._backend())
        try:
            if not capture.isOpened():
                return CameraDevice(
                    device_path=device_path,
                    name=self._device_name(device_path),
                    is_uvc_compatible=False,
                    backend=self._backend_name(),
                    usb_metadata=self._usb_metadata(device_path),
                    reason="Device does not expose an OpenCV-compatible video interface",
                )
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            pixel_format = self._fourcc(capture.get(cv2.CAP_PROP_FOURCC))
            capabilities = self._v4l2_capabilities(device_path)
            if not capabilities:
                capabilities = [CameraCapability(width, height, fps, pixel_format)]
            return CameraDevice(
                device_path=device_path,
                name=self._device_name(device_path),
                is_uvc_compatible=True,
                backend=self._backend_name(),
                usb_metadata=self._usb_metadata(device_path),
                capabilities=capabilities,
            )
        finally:
            capture.release()

    def _candidates(self) -> list[str]:
        if platform.system() == "Linux":
            return sorted(glob.glob("/dev/video*"))
        if platform.system() == "Windows":
            return [str(index) for index in range(self.max_windows_indexes)]
        return [str(index) for index in range(5)]

    @staticmethod
    def _opencv_source(device_path: str) -> str | int:
        return int(device_path) if device_path.isdigit() else device_path

    @staticmethod
    def _backend() -> int:
        if platform.system() == "Linux":
            return cv2.CAP_V4L2
        if platform.system() == "Windows":
            return cv2.CAP_DSHOW
        return cv2.CAP_ANY

    @staticmethod
    def _backend_name() -> str:
        return {"Linux": "V4L2", "Windows": "DirectShow"}.get(
            platform.system(), "OpenCV"
        )

    @staticmethod
    def _fourcc(value: float) -> str:
        code = int(value)
        decoded = "".join(chr((code >> (8 * index)) & 0xFF) for index in range(4))
        return decoded.strip("\x00") or "unknown"

    def _device_name(self, device_path: str) -> str:
        if platform.system() != "Linux":
            return f"Camera {device_path}"
        name_path = Path("/sys/class/video4linux") / Path(device_path).name / "name"
        try:
            return name_path.read_text(encoding="utf-8").strip()
        except OSError:
            return Path(device_path).name

    @staticmethod
    def _run(command: list[str]) -> str:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout if result.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def _usb_metadata(self, device_path: str) -> dict[str, str]:
        if platform.system() != "Linux" or not shutil.which("udevadm"):
            return {}
        output = self._run(
            ["udevadm", "info", "--query=property", f"--name={device_path}"]
        )
        keys = {"ID_VENDOR_ID", "ID_MODEL_ID", "ID_VENDOR", "ID_MODEL", "ID_V4L_PRODUCT"}
        metadata: dict[str, str] = {}
        for line in output.splitlines():
            key, separator, value = line.partition("=")
            if separator and key in keys:
                metadata[key.lower()] = value
        return metadata

    def _v4l2_capabilities(self, device_path: str) -> list[CameraCapability]:
        if platform.system() != "Linux" or not shutil.which("v4l2-ctl"):
            return []
        output = self._run(["v4l2-ctl", "-d", device_path, "--list-formats-ext"])
        capabilities: list[CameraCapability] = []
        pixel_format = "unknown"
        size: tuple[int, int] | None = None
        for line in output.splitlines():
            format_match = re.search(r"'([^']+)'", line)
            size_match = re.search(r"Size: Discrete (\d+)x(\d+)", line)
            fps_match = re.search(r"\((\d+(?:\.\d+)?) fps\)", line)
            if format_match and "Pixel Format" in line:
                pixel_format = format_match.group(1)
            elif size_match:
                size = (int(size_match.group(1)), int(size_match.group(2)))
            elif fps_match and size:
                capabilities.append(
                    CameraCapability(*size, float(fps_match.group(1)), pixel_format)
                )
        return capabilities
