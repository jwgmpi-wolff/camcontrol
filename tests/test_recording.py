"""Tests for manual recording sessions (start/stop burst capture)."""

from __future__ import annotations

import time

from camera_bridge.capture.base import CaptureBackend, CaptureError
from camera_bridge.recording import RecordingSession
from camera_bridge.storage.base import StorageBackend


class _FakeCaptureBackend(CaptureBackend):
    def __init__(self) -> None:
        self.calls = 0

    def get_snapshot(self) -> bytes:
        self.calls += 1
        return b"jpeg-bytes"


class _FailingCaptureBackend(CaptureBackend):
    def get_snapshot(self) -> bytes:
        raise CaptureError("camera unreachable")


class _FakeStorageBackend(StorageBackend):
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}

    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        self.saved[key] = data
        return key


def test_recording_session_start_saves_frames_until_stopped():
    backend = _FakeCaptureBackend()
    storage = _FakeStorageBackend()
    session = RecordingSession(
        "cam-1", backend, storage, poll_interval_seconds=0.01
    )

    started = session.start()
    time.sleep(0.1)
    stopped = session.stop()

    assert started is True
    assert stopped is True
    assert session.active is False
    assert len(storage.saved) > 0
    assert all("cam-1/manual/" in key for key in storage.saved)


def test_recording_session_start_twice_returns_false():
    backend = _FakeCaptureBackend()
    storage = _FakeStorageBackend()
    session = RecordingSession("cam-1", backend, storage, poll_interval_seconds=0.05)

    assert session.start() is True
    try:
        assert session.start() is False
    finally:
        session.stop()


def test_recording_session_stop_without_start_returns_false():
    backend = _FakeCaptureBackend()
    storage = _FakeStorageBackend()
    session = RecordingSession("cam-1", backend, storage)

    assert session.stop() is False


def test_recording_session_tolerates_capture_errors():
    backend = _FailingCaptureBackend()
    storage = _FakeStorageBackend()
    session = RecordingSession(
        "cam-1", backend, storage, poll_interval_seconds=0.01
    )

    session.start()
    time.sleep(0.1)
    session.stop()

    assert storage.saved == {}
