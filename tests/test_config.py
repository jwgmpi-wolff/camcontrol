from pathlib import Path

from camera_bridge.config import load_config, save_config
from camera_bridge.models import (
    AppConfig,
    AzureBlobStorageConfig,
    Hi3518eSshCameraConfig,
    LocalStorageConfig,
)


def test_load_config_missing_file_returns_defaults(tmp_path: Path):
    config = load_config(tmp_path / "does_not_exist.json")

    assert config.cameras == []
    assert isinstance(config.storage, LocalStorageConfig)


def test_save_and_load_config_roundtrip(tmp_path: Path):
    path = tmp_path / "cameras.json"
    original = AppConfig(
        cameras=[
            Hi3518eSshCameraConfig(
                id="cam-1", name="Front Yard", host="10.0.0.246", password=""
            )
        ],
        storage=LocalStorageConfig(path="./captures"),
    )

    save_config(original, path)
    loaded = load_config(path)

    assert loaded == original


def test_save_and_load_config_roundtrip_azure_blob(tmp_path: Path):
    path = tmp_path / "cameras.json"
    original = AppConfig(
        storage=AzureBlobStorageConfig(
            container="camcontrol",
            connection_string="UseDevelopmentStorage=true",
        )
    )

    save_config(original, path)
    loaded = load_config(path)

    assert loaded == original
    assert loaded.storage.provider == "azure_blob"
