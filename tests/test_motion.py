"""Tests for gateway-side motion detection (frame diffing + recording)."""

from __future__ import annotations

import io
import time

from PIL import Image

from camera_bridge.capture.base import CaptureBackend, CaptureError
from camera_bridge.models import MotionConfig
from camera_bridge.motion import MotionWatcher, frame_diff_score
from camera_bridge.storage.base import StorageBackend


def _solid_jpeg(color: tuple[int, int, int], size: tuple[int, int] = (64, 36)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_frame_diff_score_identical_frames_is_near_zero():
    frame = _solid_jpeg((10, 10, 10))

    score = frame_diff_score(frame, frame)

    assert score < 1.0


def test_frame_diff_score_very_different_frames_is_high():
    black = _solid_jpeg((0, 0, 0))
    white = _solid_jpeg((255, 255, 255))

    score = frame_diff_score(black, white)

    assert score > 100.0


class _FakeCaptureBackend(CaptureBackend):
    """Serves frames from a fixed list, repeating the last one once exhausted."""

    def __init__(self, frames: list[bytes]) -> None:
        self._frames = frames
        self._index = 0

    def get_snapshot(self) -> bytes:
        if self._index >= len(self._frames):
            raise CaptureError("exhausted")
        frame = self._frames[self._index]
        self._index += 1
        return frame


class _FakeStorageBackend(StorageBackend):
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}

    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        self.saved[key] = data
        return key


def test_motion_watcher_triggers_recording_on_frame_change():
    black = _solid_jpeg((0, 0, 0))
    white = _solid_jpeg((255, 255, 255))
    backend = _FakeCaptureBackend([black, white, white, white])
    storage = _FakeStorageBackend()
    config = MotionConfig(
        enabled=True,
        threshold=50.0,
        poll_interval_seconds=0.01,
        record_seconds=0.03,
        cooldown_seconds=60.0,
    )
    watcher = MotionWatcher(
        camera_id="cam-1", config=config, backend=backend, storage=storage
    )

    watcher.start()
    try:
        for _ in range(200):
            if storage.saved:
                break
            time.sleep(0.01)
    finally:
        watcher.stop()

    assert any("cam-1/motion/" in key for key in storage.saved)
    assert watcher.last_score > config.threshold


def test_motion_watcher_stays_idle_without_change():
    black = _solid_jpeg((0, 0, 0))
    backend = _FakeCaptureBackend([black] * 10)
    storage = _FakeStorageBackend()
    config = MotionConfig(
        enabled=True,
        threshold=50.0,
        poll_interval_seconds=0.01,
        record_seconds=0.03,
        cooldown_seconds=60.0,
    )
    watcher = MotionWatcher(
        camera_id="cam-1", config=config, backend=backend, storage=storage
    )

    watcher.start()
    time.sleep(0.15)
    watcher.stop()

    assert storage.saved == {}
