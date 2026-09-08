"""Configuration models for cameras and storage providers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MotionConfig(BaseModel):
    """Gateway-side motion detection: polls snapshots and diffs consecutive
    frames itself, independent of any motion detection built into the
    camera's own firmware. Off by default (opt-in per camera)."""

    enabled: bool = False
    # Mean per-pixel grayscale difference (0-255) across a downsampled
    # frame required to count as motion. Lower = more sensitive.
    threshold: float = 12.0
    poll_interval_seconds: float = 2.0
    record_seconds: float = 10.0
    cooldown_seconds: float = 15.0


class LiveViewConfig(BaseModel):
    """Publishes a periodically-refreshed snapshot directly onto the
    camera's own web server, so it's viewable at http://<camera-ip>/live.html
    without going through the gateway. Off by default (opt-in per camera)."""

    enabled: bool = False
    poll_interval_seconds: float = 3.0
    # Optional DDNS hostname/public IP (with port, if port-forwarded to
    # something other than 80) for viewing the feed from outside the LAN,
    # e.g. "myhome.duckdns.org:8080". Blank = use the LAN host/IP.
    public_url: str = ""


class Hi3518eSshCameraConfig(BaseModel):
    """Connection details for a Hi3518e-family camera running third-party
    custom firmware, reachable over SSH."""

    type: Literal["hi3518e_ssh"] = "hi3518e_ssh"
    id: str
    name: str
    host: str
    port: int = 22
    username: str = "root"
    password: str = ""
    remote_view_path: str = "/tmp/view"
    remote_media_dir: str = "/tmp/sd"
    motion: MotionConfig = Field(default_factory=MotionConfig)
    live_view: LiveViewConfig = Field(default_factory=LiveViewConfig)


class RtspCameraConfig(BaseModel):
    """Connection details for a camera exposing a standard RTSP stream."""

    type: Literal["rtsp"] = "rtsp"
    id: str
    name: str
    rtsp_url: str
    motion: MotionConfig = Field(default_factory=MotionConfig)


CameraConfig = Hi3518eSshCameraConfig | RtspCameraConfig


class LocalStorageConfig(BaseModel):
    provider: Literal["local"] = "local"
    path: str = "./captures"


class AzureBlobStorageConfig(BaseModel):
    """Azure Blob Storage. Prefer connection_string for simplicity; if left
    blank and account_url is set instead, DefaultAzureCredential (managed
    identity / az login / env vars) is used instead of a stored secret.
    """

    provider: Literal["azure_blob"] = "azure_blob"
    container: str
    prefix: str = "camcontrol/"
    connection_string: str = ""
    account_url: str = ""


class S3StorageConfig(BaseModel):
    provider: Literal["s3"] = "s3"
    bucket: str
    prefix: str = "camcontrol/"
    endpoint_url: str | None = None
    region: str | None = None
    access_key: str = ""
    secret_key: str = ""


class WebDavStorageConfig(BaseModel):
    provider: Literal["webdav"] = "webdav"
    base_url: str
    remote_dir: str = "camcontrol"
    username: str = ""
    password: str = ""


StorageConfig = (
    LocalStorageConfig | AzureBlobStorageConfig | S3StorageConfig | WebDavStorageConfig
)


class AppConfig(BaseModel):
    cameras: list[CameraConfig] = Field(default_factory=list)
    storage: StorageConfig = Field(default_factory=LocalStorageConfig)
