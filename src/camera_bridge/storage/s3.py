"""S3-compatible storage backend (AWS S3, MinIO, Backblaze B2, etc.)."""

from __future__ import annotations

import boto3
from botocore.config import Config as BotoConfig

from ..models import S3StorageConfig
from .base import StorageBackend, StorageError


class S3Storage(StorageBackend):
    def __init__(self, config: S3StorageConfig) -> None:
        self._config = config
        session = boto3.session.Session()
        self._client = session.client(
            "s3",
            endpoint_url=config.endpoint_url,
            region_name=config.region,
            aws_access_key_id=config.access_key or None,
            aws_secret_access_key=config.secret_key or None,
            config=BotoConfig(signature_version="s3v4"),
        )

    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        object_key = f"{self._config.prefix.rstrip('/')}/{key}".lstrip("/")
        try:
            self._client.put_object(
                Bucket=self._config.bucket,
                Key=object_key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"S3 put_object failed for {object_key}: {exc}") from exc
        return f"s3://{self._config.bucket}/{object_key}"
