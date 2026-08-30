"""Azure Blob Storage client for snapshots and video clips."""

from __future__ import annotations

import logging
import mimetypes
from datetime import UTC, datetime
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class BlobStorageClient:
    def __init__(
        self,
        connection_string: str | None = None,
        account_name: str | None = None,
        container_name: str = "camera-recordings",
    ) -> None:
        self.container_name = container_name
        self._client = None

        if not connection_string and not account_name:
            LOGGER.warning("No Azure Storage credentials; blob upload disabled")
            return

        try:
            from azure.storage.blob import BlobServiceClient
            if connection_string:
                svc = BlobServiceClient.from_connection_string(connection_string)
            else:
                # Prefer managed identity / DefaultAzureCredential
                from azure.identity import DefaultAzureCredential
                svc = BlobServiceClient(
                    account_url=f"https://{account_name}.blob.core.windows.net",
                    credential=DefaultAzureCredential(),
                )
            self._client = svc.get_container_client(container_name)
            # Ensure container exists
            if not self._client.exists():
                self._client.create_container()
            LOGGER.info("Connected to Azure Blob Storage container: %s", container_name)
        except Exception as exc:
            LOGGER.error("Blob Storage init failed: %s", exc)

    def upload_file(self, local_path: str, blob_name: str | None = None) -> str | None:
        """Upload a file and return its blob URL, or None on failure."""
        if not self._client:
            return None
        path = Path(local_path)
        if not path.exists():
            LOGGER.warning("File not found: %s", local_path)
            return None

        name = blob_name or f"{datetime.now(UTC).strftime('%Y/%m/%d')}/{path.name}"
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        try:
            from azure.storage.blob import ContentSettings
            with path.open("rb") as fh:
                self._client.upload_blob(
                    name=name,
                    data=fh,
                    content_settings=ContentSettings(content_type=content_type),
                    overwrite=True,
                )
            url = f"{self._client.url}/{name}"
            LOGGER.info("Uploaded %s → %s", path.name, url)
            return url
        except Exception as exc:
            LOGGER.error("Upload failed for %s: %s", local_path, exc)
            return None

    def upload_bytes(self, data: bytes, blob_name: str, content_type: str = "image/jpeg") -> str | None:
        if not self._client:
            return None
        try:
            from azure.storage.blob import ContentSettings
            self._client.upload_blob(
                name=blob_name,
                data=data,
                content_settings=ContentSettings(content_type=content_type),
                overwrite=True,
            )
            return f"{self._client.url}/{blob_name}"
        except Exception as exc:
            LOGGER.error("Blob bytes upload failed: %s", exc)
            return None
