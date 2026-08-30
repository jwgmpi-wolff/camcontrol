"""
Multi-camera registry — persists owned camera records to cameras.json.
Never stores credentials; only device metadata and last-known stream state.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

# Stored adjacent to the package root, outside src/ so it survives code updates
_REGISTRY_PATH = Path(__file__).parent.parent.parent / "cameras.json"
_lock = threading.Lock()


def _load() -> dict[str, dict]:
    if not _REGISTRY_PATH.exists():
        return {}
    try:
        return json.loads(_REGISTRY_PATH.read_text())
    except Exception as exc:
        LOGGER.error("Failed to load camera registry: %s", exc)
        return {}


def _save(data: dict[str, dict]) -> None:
    _REGISTRY_PATH.write_text(json.dumps(data, indent=2))


def list_cameras() -> list[dict]:
    with _lock:
        return list(_load().values())


def get_camera(device_id: str) -> dict | None:
    with _lock:
        return _load().get(device_id)


def upsert_camera(device_id: str, meta: dict[str, Any]) -> dict:
    """Add or update a camera record. Returns the saved record."""
    with _lock:
        data = _load()
        existing = data.get(device_id, {})
        existing.update(meta)
        existing["device_id"] = device_id
        data[device_id] = existing
        _save(data)
        return existing


def remove_camera(device_id: str) -> bool:
    with _lock:
        data = _load()
        if device_id not in data:
            return False
        del data[device_id]
        _save(data)
        return True


def import_from_yi_devices(devices: list[dict]) -> list[dict]:
    """Bulk-import cameras returned by yi_cloud.get_devices(). Returns list of upserted records."""
    imported = []
    for dev in devices:
        did = dev.get("device_id") or dev.get("did") or dev.get("id") or ""
        if not did:
            continue
        record = upsert_camera(did, {
            "name": dev.get("name") or dev.get("device_name") or f"Camera {did[:8]}",
            "mac": dev.get("mac", ""),
            "model": dev.get("model") or dev.get("device_model", ""),
            "ip": dev.get("ip") or dev.get("local_ip", ""),
            "yi_raw": dev,
        })
        imported.append(record)
    return imported
