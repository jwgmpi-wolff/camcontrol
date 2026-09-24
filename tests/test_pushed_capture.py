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