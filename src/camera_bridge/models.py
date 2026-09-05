"""Configuration models for cameras and storage providers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class YiHackV3SshCameraConfig(BaseModel):
    """Connection details for a yi-hack-v3 (Hi3518e) camera reachable over SSH."""

    type: Literal["yi_hack_v3_ssh"] = "yi_hack_v3_ssh"
    id: str
    name: str
    host: str
    port: int = 22
    username: str = "root"
    password: str = ""
    remote_view_path: str = "/tmp/view"
    remote_media_dir: str = "/tmp/sd"


class RtspCameraConfig(BaseModel):
    """Connection details for a camera exposing a standard RTSP stream."""

    type: Literal["rtsp"] = "rtsp"
    id: str
    name: str
    rtsp_url: str


CameraConfig = YiHackV3SshCameraConfig | RtspCameraConfig


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
