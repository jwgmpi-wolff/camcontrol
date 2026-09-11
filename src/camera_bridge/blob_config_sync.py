"""Optional Azure Blob-backed persistence for local config JSON files.

App Service Linux's native Azure Files mount authenticates with the storage
account key; tenants that enforce "disallow shared key access" (a common
security baseline policy) silently break that mount. This module instead
syncs individual config files to/from Blob Storage using Azure AD
(DefaultAzureCredential + RBAC role assignment), which keeps working with
shared key access disabled. Only active when CONFIG_BLOB_ACCOUNT_URL is set;
with it unset, callers see local-file-only behavior exactly as before.
"""

from __future__ import annotations

import os
from pathlib import Path

_ACCOUNT_URL = os.environ.get("CONFIG_BLOB_ACCOUNT_URL", "")
_CONTAINER = os.environ.get("CONFIG_BLOB_CONTAINER", "config")

_container_client_cache = None


def enabled() -> bool:
    return bool(_ACCOUNT_URL)


def _container_client():
    global _container_client_cache
    if _container_client_cache is not None:
        return _container_client_cache
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    service = BlobServiceClient(_ACCOUNT_URL, credential=DefaultAzureCredential())
    container = service.get_container_client(_CONTAINER)
    try:
        container.create_container()
    except Exception:  # noqa: BLE001 - likely "already exists"; not fatal either way
        pass
    _container_client_cache = container
    return _container_client_cache


def download_if_configured(local_path: Path) -> None:
    """Best-effort: pull the blob named after local_path into local_path."""
    if not enabled():
        return
    try:
        blob = _container_client().get_blob_client(local_path.name)
        data = blob.download_blob().readall()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
    except Exception:  # noqa: BLE001
        pass  # no blob yet (first run) or transient error -- keep local state


def upload_if_configured(local_path: Path) -> None:
    """Best-effort: push local_path's current contents up as a blob."""
    if not enabled() or not local_path.exists():
        return
    try:
        _container_client().upload_blob(
            local_path.name, local_path.read_bytes(), overwrite=True
        )
    except Exception:  # noqa: BLE001
        pass  # local file remains source of truth for this instance either way
