"""Azure Blob Storage backend — prioritized default cloud storage provider.

Uses a connection string when provided (simplest for a self-hosted personal
setup); otherwise falls back to DefaultAzureCredential against account_url
(managed identity, `az login`, or environment-based auth), matching the
"secure by default, no hardcoded secret" guidance for Azure workloads.
"""

from __future__ import annotations

from azure.storage.blob import BlobServiceClient, ContentSettings

from ..models import AzureBlobStorageConfig
from .base import StorageBackend, StorageError


class AzureBlobStorage(StorageBackend):
    def __init__(self, config: AzureBlobStorageConfig) -> None:
        self._config = config
        if config.connection_string:
            self._client = BlobServiceClient.from_connection_string(
                config.connection_string
            )
        elif config.account_url:
            from azure.identity import DefaultAzureCredential

            self._client = BlobServiceClient(
                account_url=config.account_url, credential=DefaultAzureCredential()
            )
        else:
            raise StorageError(
                "Azure Blob Storage requires either connection_string or account_url"
            )
        self._container = self._client.get_container_client(config.container)

    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        blob_name = f"{self._config.prefix.rstrip('/')}/{key}".lstrip("/")
        try:
            self._container.upload_blob(
                name=blob_name,
                data=data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Azure Blob upload failed for {blob_name}: {exc}") from exc
        return f"{self._config.container}/{blob_name}"
