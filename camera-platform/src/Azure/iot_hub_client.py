"""Azure IoT Hub telemetry client for the camera platform."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

LOGGER = logging.getLogger(__name__)


class IotHubClient:
    def __init__(self, connection_string: str | None = None) -> None:
        if not connection_string:
            LOGGER.warning("IOTHUB_DEVICE_CONNECTION_STRING not set; telemetry disabled")
            self._client = None
            return
        try:
            from azure.iot.device import IoTHubDeviceClient
            self._client = IoTHubDeviceClient.create_from_connection_string(connection_string)
            self._client.connect()
            LOGGER.info("Connected to Azure IoT Hub")
        except Exception as exc:
            LOGGER.error("IoT Hub connection failed: %s", exc)
            self._client = None

    def send_telemetry(self, payload: dict[str, Any]) -> None:
        if not self._client:
            return
        try:
            from azure.iot.device import Message
            envelope = {"timestamp": datetime.now(UTC).isoformat(), **payload}
            msg = Message(json.dumps(envelope))
            msg.content_type = "application/json"
            msg.content_encoding = "utf-8"
            self._client.send_message(msg)
        except Exception as exc:
            LOGGER.error("Telemetry send failed: %s", exc)

    def send_health(
        self,
        *,
        camera_ip: str,
        online: bool,
        streaming: bool,
        recording: bool,
        storage_target: str,
        last_snapshot: str | None = None,
        error: str | None = None,
    ) -> None:
        self.send_telemetry({
            "event": "cameraHealth",
            "cameraIp": camera_ip,
            "online": online,
            "streaming": streaming,
            "recording": recording,
            "storageTarget": storage_target,
            "lastSnapshotTime": last_snapshot,
            "error": error,
        })

    def disconnect(self) -> None:
        if self._client:
            try:
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
