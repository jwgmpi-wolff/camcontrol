"""Build the correct storage backend for the configured provider."""

from __future__ import annotations

from ..models import (
    AzureBlobStorageConfig,
    LocalStorageConfig,
    S3StorageConfig,
    StorageConfig,
    WebDavStorageConfig,
)
from .azure_blob import AzureBlobStorage
from .base import StorageBackend
from .local import LocalStorage
from .s3 import S3Storage
from .webdav import WebDavStorage


def build_storage_backend(config: StorageConfig) -> StorageBackend:
    if isinstance(config, AzureBlobStorageConfig):
        return AzureBlobStorage(config)
    if isinstance(config, LocalStorageConfig):
        return LocalStorage(config)
    if isinstance(config, S3StorageConfig):
        return S3Storage(config)
    if isinstance(config, WebDavStorageConfig):
        return WebDavStorage(config)
    raise ValueError(f"Unsupported storage config type: {type(config)!r}")
