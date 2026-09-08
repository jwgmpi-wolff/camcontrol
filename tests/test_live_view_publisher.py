"""Tests for the live-view publisher (pushes snapshots to the camera's own
web root so it's viewable directly at http://<camera-ip>/live.html)."""

from __future__ import annotations

import time

from camera_bridge.capture.base import CaptureBackend, CaptureError
from camera_bridge.live_view_publisher import (
    LiveViewPublisher,
    _httpd_health_command,
    _render_live_html,
)
from camera_bridge.models import Hi3518eSshCameraConfig


class _FakeCaptureBackend(CaptureBackend):
    def __init__(self) -> None:
        self.calls = 0

    def get_snapshot(self) -> bytes:
        self.calls += 1
        return b"jpeg-bytes"


class _FailingCaptureBackend(CaptureBackend):
    def get_snapshot(self) -> bytes:
        raise CaptureError("camera unreachable")


def test_live_page_uses_subsecond_refresh_interval():
    html = _render_live_html(0.5)

    assert "}, 500);" in html
    assert "__REFRESH_INTERVAL_MS__" not in html


def test_httpd_health_command_restarts_after_stale_connection_limit():
    command = _httpd_health_command(20)

    assert '$6 == "CLOSE_WAIT"' in command
    assert '[ "$stale" -ge 20 ]' in command
    assert "awk '$4 == \"lwsws\" {print $1}'" in command
    assert "rm -f /tmp/.lwsts-lock" in command
    assert "lwsws -D" in command


def test_live_view_publisher_start_stop_does_not_raise(monkeypatch):
    cfg = Hi3518eSshCameraConfig(id="cam-1", name="Cam 1", host="10.0.0.1")
    backend = _FakeCaptureBackend()
    publisher = LiveViewPublisher("cam-1", cfg, backend, poll_interval_seconds=0.01)

    # Avoid real network calls: stub out the SSH-dependent pieces.
    monkeypatch.setattr(publisher, "_deploy_page", lambda: None)
    pushed = []
    monkeypatch.setattr(publisher, "_push_frame", lambda jpeg: pushed.append(jpeg))

    publisher.start()
    time.sleep(0.1)
    publisher.stop()

    assert len(pushed) > 0
    assert all(p == b"jpeg-bytes" for p in pushed)
    assert publisher.last_push_ok is True


def test_live_view_publisher_tolerates_capture_errors(monkeypatch):
    cfg = Hi3518eSshCameraConfig(id="cam-1", name="Cam 1", host="10.0.0.1")
    backend = _FailingCaptureBackend()
    publisher = LiveViewPublisher("cam-1", cfg, backend, poll_interval_seconds=0.01)

    monkeypatch.setattr(publisher, "_deploy_page", lambda: None)
    monkeypatch.setattr(publisher, "_push_frame", lambda jpeg: None)

    publisher.start()
    time.sleep(0.1)
    publisher.stop()

    assert publisher.last_push_ok is False


def test_live_view_publisher_start_is_idempotent(monkeypatch):
    cfg = Hi3518eSshCameraConfig(id="cam-1", name="Cam 1", host="10.0.0.1")
    backend = _FakeCaptureBackend()
    publisher = LiveViewPublisher("cam-1", cfg, backend, poll_interval_seconds=1.0)

    monkeypatch.setattr(publisher, "_deploy_page", lambda: None)
    monkeypatch.setattr(publisher, "_push_frame", lambda jpeg: None)

    publisher.start()
    first_thread = publisher._thread
    publisher.start()

    assert publisher._thread is first_thread
    publisher.stop()
