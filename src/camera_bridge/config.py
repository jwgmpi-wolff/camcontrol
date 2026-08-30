"""Environment-backed application configuration."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _as_int(name: str, value: str | None, default: int, minimum: int) -> int:
    result = default if value is None else int(value)
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


@dataclass(frozen=True, slots=True)
class Settings:
    iothub_device_connection_string: str | None
    camera_device_path: str
    camera_rtsp_url: str | None
    camera_fcc_id: str | None
    camera_model: str | None
    stream_enabled: bool
    stream_protocol: str
    stream_port: int
    stream_username: str | None
    stream_password: str | None
    snapshot_interval_seconds: int
    snapshot_directory: Path
    api_enabled: bool
    api_host: str
    api_port: int
    api_key: str | None
    log_level: str

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Settings":
        load_dotenv(dotenv_path=env_file, override=False)
        default_camera = "/dev/video0" if platform.system() == "Linux" else "0"
        protocol = os.getenv("STREAM_PROTOCOL", "rtsp").strip().lower()
        if protocol not in {"rtsp", "webrtc"}:
            raise ValueError("STREAM_PROTOCOL must be 'rtsp' or 'webrtc'")

        settings = cls(
            iothub_device_connection_string=os.getenv(
                "IOTHUB_DEVICE_CONNECTION_STRING"
            ),
            camera_device_path=os.getenv("CAMERA_DEVICE_PATH", default_camera),
            camera_rtsp_url=os.getenv("CAMERA_RTSP_URL") or None,
            camera_fcc_id=os.getenv("CAMERA_FCC_ID") or None,
            camera_model=os.getenv("CAMERA_MODEL") or None,
            stream_enabled=_as_bool(os.getenv("STREAM_ENABLED"), default=False),
            stream_protocol=protocol,
            stream_port=_as_int("STREAM_PORT", os.getenv("STREAM_PORT"), 8554, 1),
            stream_username=os.getenv("STREAM_USERNAME"),
            stream_password=os.getenv("STREAM_PASSWORD"),
            snapshot_interval_seconds=_as_int(
                "SNAPSHOT_INTERVAL_SECONDS",
                os.getenv("SNAPSHOT_INTERVAL_SECONDS"),
                0,
                0,
            ),
            snapshot_directory=Path(
                os.getenv("SNAPSHOT_DIRECTORY", "./data/snapshots")
            ),
            api_enabled=_as_bool(os.getenv("API_ENABLED"), default=True),
            api_host=os.getenv("API_HOST", "0.0.0.0"),
            api_port=_as_int("API_PORT", os.getenv("API_PORT"), 8080, 1),
            api_key=os.getenv("API_KEY") or None,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.stream_port > 65535:
            raise ValueError("STREAM_PORT must be at most 65535")
        if bool(self.stream_username) != bool(self.stream_password):
            raise ValueError(
                "STREAM_USERNAME and STREAM_PASSWORD must be configured together"
            )
        if self.stream_enabled and self.stream_protocol == "rtsp":
            if not self.stream_username or not self.stream_password:
                raise ValueError("RTSP streaming requires username and password")

    @property
    def effective_camera_source(self) -> str:
        """RTSP URL if provided, otherwise the local device path."""
        return self.camera_rtsp_url or self.camera_device_path

    @property
    def has_iot_edge_environment(self) -> bool:
        return bool(os.getenv("IOTEDGE_WORKLOADURI") and os.getenv("IOTEDGE_DEVICEID"))
