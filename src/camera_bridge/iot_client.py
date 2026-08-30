"""Azure IoT Hub device/module communication and command dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from azure.iot.device import Message, MethodResponse
from azure.iot.device.aio import IoTHubDeviceClient, IoTHubModuleClient

from .config import Settings

LOGGER = logging.getLogger(__name__)
MethodHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
TwinHandler = Callable[[dict[str, Any]], Awaitable[None]]


class CameraIoTClient:
    def __init__(
        self,
        settings: Settings,
        method_handlers: dict[str, MethodHandler],
        twin_handler: TwinHandler,
    ) -> None:
        self.settings = settings
        self.method_handlers = method_handlers
        self.twin_handler = twin_handler
        self._client: IoTHubDeviceClient | IoTHubModuleClient | None = None
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.has_iot_edge_environment
            or self.settings.iothub_device_connection_string
        )

    async def connect(self) -> None:
        if self.settings.has_iot_edge_environment:
            self._client = IoTHubModuleClient.create_from_edge_environment()
        elif self.settings.iothub_device_connection_string:
            self._client = IoTHubDeviceClient.create_from_connection_string(
                self.settings.iothub_device_connection_string
            )
        else:
            raise RuntimeError(
                "No IoT Edge environment or IOTHUB_DEVICE_CONNECTION_STRING is configured"
            )
        await self._client.connect()
        self._tasks = [
            asyncio.create_task(self._method_loop(), name="iot-direct-methods"),
            asyncio.create_task(self._twin_loop(), name="iot-twin-patches"),
        ]
        LOGGER.info("Connected to Azure IoT", extra={"event": "iot_connected"})

    async def disconnect(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._client:
            await self._client.disconnect()
            self._client = None

    async def send_telemetry(self, payload: dict[str, Any]) -> None:
        if not self._client:
            return
        envelope = {
            "timestamp": datetime.now(UTC).isoformat(),
            **payload,
        }
        message = Message(json.dumps(envelope, default=str))
        message.content_type = "application/json"
        message.content_encoding = "utf-8"
        await self._client.send_message(message)

    async def report_properties(self, patch: dict[str, Any]) -> None:
        if self._client:
            await self._client.patch_twin_reported_properties(patch)

    async def _method_loop(self) -> None:
        assert self._client is not None
        while True:
            request = await self._client.receive_method_request()
            LOGGER.info(
                "Direct method received",
                extra={"event": "direct_method", "method": request.name},
            )
            status = 200
            try:
                handler = self.method_handlers.get(request.name)
                if not handler:
                    status = 404
                    payload = {"error": f"Unknown method: {request.name}"}
                else:
                    request_payload = request.payload or {}
                    if not isinstance(request_payload, dict):
                        raise ValueError("Method payload must be a JSON object")
                    payload = await handler(request_payload)
            except ValueError as exc:
                status = 400
                payload = {"error": str(exc)}
            except NotImplementedError as exc:
                status = 501
                payload = {"error": str(exc)}
            except Exception:
                status = 500
                payload = {"error": "Command failed; inspect edge module logs"}
                LOGGER.exception(
                    "Direct method failed",
                    extra={"event": "direct_method_failed", "method": request.name},
                )
            response = MethodResponse.create_from_method_request(
                request, status, payload
            )
            await self._client.send_method_response(response)
            await self.send_telemetry(
                {"event": "directMethodAudit", "method": request.name, "status": status}
            )

    async def _twin_loop(self) -> None:
        assert self._client is not None
        twin = await self._client.get_twin()
        desired = twin.get("desired", {})
        if desired:
            await self.twin_handler(desired)
        while True:
            patch = await self._client.receive_twin_desired_properties_patch()
            await self.twin_handler(patch)
