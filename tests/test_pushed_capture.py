from types import SimpleNamespace

from fastapi.testclient import TestClient

from camera_bridge.api import (
    _PUSHED_SNAPSHOT_MAX_AGE_SECONDS,
    app,
    state,
)


def test_capture_prefers_relay_snapshot(monkeypatch):
    from camera_bridge import api

    camera_id = "relay-camera"
    snapshot = b"\xff\xd8relay-frame\xff\xd9"
    state.remember_pushed_snapshot(camera_id, snapshot)

    class Storage:
        def save(self, key: str, data: bytes) -> str:
            assert data == snapshot
            return key

    monkeypatch.setattr(state, "storage_backend", lambda: Storage())
    monkeypatch.setattr(
        state,
        "capture_backend_for",
        lambda _: object(),
    )
    try:
        result = api.capture_and_store(camera_id)
    finally:
        state.pushed_snapshots.pop(camera_id, None)
        state._pushed_snapshot_times.pop(camera_id, None)

    assert result.camera_id == camera_id


def test_stale_relay_snapshot_is_discarded(monkeypatch):
    camera_id = "stale-relay-camera"
    snapshot = b"\xff\xd8stale-frame\xff\xd9"
    now = 1000.0
    monkeypatch.setattr("camera_bridge.api.time.monotonic", lambda: now)
    state.remember_pushed_snapshot(camera_id, snapshot)

    now += _PUSHED_SNAPSHOT_MAX_AGE_SECONDS + 1

    assert state.fresh_pushed_snapshot(camera_id) is None
    assert camera_id not in state.pushed_snapshots
    assert camera_id not in state._pushed_snapshot_times


def test_refresh_endpoint_invalidates_all_relay_snapshots(monkeypatch):
    monkeypatch.setenv("CAMCONTROL_API_KEY", "test-key")
    state.remember_pushed_snapshot("camera-1", b"frame-1")
    state.remember_pushed_snapshot("camera-2", b"frame-2")

    response = TestClient(app).post(
        "/api/cameras/refresh",
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "refresh_requested"
    assert response.json()["snapshots_invalidated"] == 2
    assert state.pushed_snapshots == {}
    assert state._pushed_snapshot_times == {}


def test_health_reports_end_to_end_feed_freshness(monkeypatch):
    now = 1000.0
    monkeypatch.setattr("camera_bridge.api.time.monotonic", lambda: now)
    monkeypatch.setattr(
        state.config,
        "cameras",
        [SimpleNamespace(id="camera-1"), SimpleNamespace(id="camera-2")],
    )
    state.pushed_snapshots.clear()
    state._pushed_snapshot_times.clear()
    camera_ids = [camera.id for camera in state.config.cameras]
    state.remember_pushed_snapshot(camera_ids[0], b"frame")

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    health = response.json()
    assert health["feeds_expected"] == len(camera_ids)
    assert health["feeds_live"] == 1
    assert health["all_feeds_live"] is (len(camera_ids) == 1)

    now += _PUSHED_SNAPSHOT_MAX_AGE_SECONDS + 1
    stale_health = TestClient(app).get("/api/health").json()

    assert stale_health["feeds_live"] == 0
    assert stale_health["all_feeds_live"] is False