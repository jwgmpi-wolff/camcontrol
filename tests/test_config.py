from __future__ import annotations

import pytest

from camera_bridge.config import Settings


ENV_KEYS = (
    "IOTHUB_DEVICE_CONNECTION_STRING",
    "CAMERA_DEVICE_PATH",
    "STREAM_ENABLED",
    "STREAM_PROTOCOL",
    "STREAM_PORT",
    "STREAM_USERNAME",
    "STREAM_PASSWORD",
    "SNAPSHOT_INTERVAL_SECONDS",
    "SNAPSHOT_DIRECTORY",
    "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_disable_streaming() -> None:
    settings = Settings.from_env()

    assert settings.stream_enabled is False
    assert settings.stream_protocol == "rtsp"
    assert settings.stream_port == 8554


def test_enabled_rtsp_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STREAM_ENABLED", "true")

    with pytest.raises(ValueError, match="requires username and password"):
        Settings.from_env()


def test_rejects_invalid_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STREAM_PORT", "70000")

    with pytest.raises(ValueError, match="at most 65535"):
        Settings.from_env()


def test_accepts_authenticated_rtsp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STREAM_ENABLED", "true")
    monkeypatch.setenv("STREAM_USERNAME", "viewer")
    monkeypatch.setenv("STREAM_PASSWORD", "not-a-real-secret")

    settings = Settings.from_env()

    assert settings.stream_enabled is True
    assert settings.stream_username == "viewer"