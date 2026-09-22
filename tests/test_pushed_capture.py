from camera_bridge.api import state


def test_capture_prefers_relay_snapshot(monkeypatch):
    from camera_bridge import api

    camera_id = "relay-camera"
    snapshot = b"\xff\xd8relay-frame\xff\xd9"
    state.pushed_snapshots[camera_id] = snapshot

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

    assert result.camera_id == camera_id