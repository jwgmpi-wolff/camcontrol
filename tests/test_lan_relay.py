"""Tests for the local constrained-camera relay authentication."""

from __future__ import annotations

import hashlib
import hmac

from fastapi.testclient import TestClient

from camera_bridge import lan_relay
from camera_bridge.lan_relay import (
    RELAY_FEED_MAX_AGE_SECONDS,
    app,
    camera_key_for,
    camera_key_is_accepted,
    camera_key_is_valid,
    configured_cameras,
    relay_feed_health,
)


def test_camera_key_validation_accepts_derived_key():
    master_key = "test-master-key"
    camera_id = "yhs3017-1"
    camera_key = hmac.new(
        master_key.encode(), camera_id.encode(), hashlib.sha256
    ).hexdigest()

    assert camera_key_is_valid(camera_id, camera_key, master_key)


def test_camera_key_validation_rejects_wrong_camera_or_key():
    master_key = "test-master-key"
    camera_key = hmac.new(
        master_key.encode(), b"yhs3017-1", hashlib.sha256
    ).hexdigest()

    assert not camera_key_is_valid("yhs3017-2", camera_key, master_key)
    assert not camera_key_is_valid("yhs3017-1", "wrong", master_key)
    assert not camera_key_is_valid("yhs3017-1", camera_key, "")


def test_camera_key_for_matches_the_gateway_derivation():
    master_key = "test-master-key"

    assert camera_key_for("yhs3017-1", master_key) == hmac.new(
        master_key.encode(), b"yhs3017-1", hashlib.sha256
    ).hexdigest()


def test_relay_defers_validation_to_gateway_without_local_master_key():
    assert camera_key_is_accepted("yhs3017-1", "camera-provided-key", "")
    assert not camera_key_is_accepted("yhs3017-1", None, "")


def test_configured_cameras_parses_multiple_camera_urls(monkeypatch):
    monkeypatch.setenv(
        "CAMCONTROL_RELAY_CAMERAS",
        "yhs3017-1=http://10.0.0.246/live.jpg,yhs3017-2=http://10.0.0.252/live.jpg",
    )

    assert configured_cameras() == [
        ("yhs3017-1", "http://10.0.0.246/live.jpg"),
        ("yhs3017-2", "http://10.0.0.252/live.jpg"),
    ]


def test_configured_cameras_accepts_ssh_preview_sources(monkeypatch):
    monkeypatch.setenv(
        "CAMCONTROL_RELAY_CAMERAS",
        "yhs3017-1=ssh://10.0.0.246,yhs3017-2=ssh://10.0.0.252",
    )

    assert configured_cameras() == [
        ("yhs3017-1", "ssh://10.0.0.246"),
        ("yhs3017-2", "ssh://10.0.0.252"),
    ]


def test_relay_health_tracks_successful_camera_forward(monkeypatch):
    now = 1000.0
    monkeypatch.setattr("camera_bridge.lan_relay.time.monotonic", lambda: now)
    monkeypatch.delenv("CAMCONTROL_API_KEY", raising=False)
    lan_relay._received_at.clear()
    lan_relay._forwarded_at.clear()
    lan_relay._forward_errors.clear()

    async def successful_forward(
        camera_id: str, payload: bytes, camera_key: str
    ) -> None:
        assert camera_id == "yhs3017-1"
        assert payload == b"\xff\xd8frame\xff\xd9"
        assert camera_key == "camera-key"

    monkeypatch.setattr(lan_relay, "forward_snapshot", successful_forward)
    response = TestClient(app).post(
        "/api/cameras/yhs3017-1/push-snapshot",
        content=b"\xff\xd8frame\xff\xd9",
        headers={"X-Camera-Key": "camera-key"},
    )

    assert response.status_code == 200
    assert relay_feed_health()["all_feeds_forwarding"] is True

    now += RELAY_FEED_MAX_AGE_SECONDS + 1
    health = relay_feed_health()

    assert health["all_feeds_forwarding"] is False
    assert health["feeds"]["yhs3017-1"]["receiving"] is False
    assert health["feeds"]["yhs3017-1"]["forwarding"] is False