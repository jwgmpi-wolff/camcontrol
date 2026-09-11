"""Load and save the application config (cameras + storage provider) as JSON."""

from __future__ import annotations

import json
from pathlib import Path

from .blob_config_sync import download_if_configured, upload_if_configured
from .models import AppConfig

DEFAULT_CONFIG_PATH = Path("config/cameras.json")


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    download_if_configured(path)
    if not path.exists():
        return AppConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)


def save_config(config: AppConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config.model_dump(), indent=2),
        encoding="utf-8",
    )
    upload_if_configured(path)
