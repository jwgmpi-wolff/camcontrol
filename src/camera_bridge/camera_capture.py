"""Thread-safe OpenCV camera capture operations."""

from __future__ import annotations

import platform
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2


class CameraCaptureError(RuntimeError):
    pass


class CameraCapture:
    def __init__(self, device_path: str) -> None:
        self.device_path = device_path
        self._capture: cv2.VideoCapture | None = None
        self._lock = threading.RLock()
        self._writer: cv2.VideoWriter | None = None
        self._recording_path: Path | None = None
        self._recording_stop = threading.Event()
        self._recording_thread: threading.Thread | None = None

    def open(self) -> None:
        with self._lock:
            if self._capture and self._capture.isOpened():
                return
            source: str | int = (
                int(self.device_path) if self.device_path.isdigit() else self.device_path
            )
            backend = {
                "Linux": cv2.CAP_V4L2,
                "Windows": cv2.CAP_DSHOW,
            }.get(platform.system(), cv2.CAP_ANY)
            capture = cv2.VideoCapture(source, backend)
            if not capture.isOpened():
                capture.release()
                raise CameraCaptureError(
                    f"Unable to open supported video interface {self.device_path}"
                )
            self._capture = capture

    def close(self) -> None:
        self.stop_recording()
        with self._lock:
            if self._capture:
                self._capture.release()
                self._capture = None

    def read_frame(self) -> Any:
        with self._lock:
            self.open()
            assert self._capture is not None
            success, frame = self._capture.read()
            if not success or frame is None:
                raise CameraCaptureError("Camera returned no frame")
            return frame

    def capture_snapshot(self, directory: Path) -> tuple[Path, datetime]:
        frame = self.read_frame()
        timestamp = datetime.now(UTC)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"snapshot-{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}.jpg"
        if not cv2.imwrite(str(path), frame):
            raise CameraCaptureError(f"Failed to write snapshot to {path}")
        return path, timestamp

    def set_profile(self, width: int, height: int, fps: float) -> dict[str, float | int]:
        if width <= 0 or height <= 0 or fps <= 0:
            raise ValueError("width, height, and fps must be positive")
        with self._lock:
            self.open()
            assert self._capture is not None
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self._capture.set(cv2.CAP_PROP_FPS, fps)
            actual = {
                "width": int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": float(self._capture.get(cv2.CAP_PROP_FPS)),
            }
            if actual["width"] != width or actual["height"] != height:
                raise CameraCaptureError(
                    f"Requested profile is unsupported; device selected {actual}"
                )
            return actual

    def start_recording(self, directory: Path, prefix: str = "recording") -> Path:
        with self._lock:
            if self._writer is not None:
                raise CameraCaptureError("Recording already in progress")
            self.open()
            assert self._capture is not None
            width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(self._capture.get(cv2.CAP_PROP_FPS)) or 15.0
            directory.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(UTC)
            path = directory / f"{prefix}-{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}.avi"
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
            if not writer.isOpened():
                raise CameraCaptureError(f"Failed to open video writer at {path}")
            self._writer = writer
            self._recording_path = path
            self._recording_stop.clear()
        self._recording_thread = threading.Thread(
            target=self._recording_loop, name="recorder", daemon=True
        )
        self._recording_thread.start()
        return path

    def stop_recording(self) -> Path | None:
        self._recording_stop.set()
        if self._recording_thread:
            self._recording_thread.join(timeout=5)
            self._recording_thread = None
        with self._lock:
            if self._writer is None:
                return None
            self._writer.release()
            path = self._recording_path
            self._writer = None
            self._recording_path = None
            return path

    @property
    def recording(self) -> bool:
        return self._writer is not None

    def _recording_loop(self) -> None:
        while not self._recording_stop.is_set():
            with self._lock:
                if self._writer is None:
                    break
                if self._capture and self._capture.isOpened():
                    success, frame = self._capture.read()
                    if success and frame is not None:
                        self._writer.write(frame)
            time.sleep(0.001)

    def __enter__(self) -> "CameraCapture":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
