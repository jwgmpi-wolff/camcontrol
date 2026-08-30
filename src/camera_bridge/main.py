"""Camera bridge process entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import threading
from typing import Any

from .camera_capture import CameraCapture
from .camera_discovery import CameraDevice, CameraDiscovery
from .config import Settings
from .iot_client import CameraIoTClient
from .logging_config import configure_logging
from .stream_server import StreamServer, StreamServerError

LOGGER = logging.getLogger(__name__)


class CameraBridge:
    def __init__(self, settings: Settings, device: CameraDevice) -> None:
        self.settings = settings
        self.device = device
        self.capture = CameraCapture(device.device_path)
        self.stream = StreamServer(
            device.device_path,
            settings.stream_protocol,
            settings.stream_port,
            settings.stream_username,
            settings.stream_password,
        )
        self.iot = CameraIoTClient(
            settings,
            {
                "startStream": self.start_stream,
                "stopStream": self.stop_stream,
                "captureSnapshot": self.capture_snapshot,
                "getDeviceInfo": self.get_device_info,
                "setStreamProfile": self.set_stream_profile,
                "startRecording": self.start_recording,
                "stopRecording": self.stop_recording,
            },
            self.apply_desired_properties,
        )

    async def start_stream(self, _payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.stream_enabled:
            raise ValueError("Streaming is disabled by local STREAM_ENABLED policy")
        try:
            endpoint = await asyncio.to_thread(self.stream.start)
        except StreamServerError as exc:
            raise NotImplementedError(str(exc)) from exc
        return {"streaming": True, "endpoint": endpoint.to_dict()}

    async def stop_stream(self, _payload: dict[str, Any]) -> dict[str, Any]:
        await asyncio.to_thread(self.stream.stop)
        return {"streaming": False}

    async def capture_snapshot(self, _payload: dict[str, Any]) -> dict[str, Any]:
        path, timestamp = await asyncio.to_thread(
            self.capture.capture_snapshot, self.settings.snapshot_directory
        )
        result = {"path": str(path), "timestamp": timestamp.isoformat()}
        await self.iot.send_telemetry({"event": "snapshotCaptured", **result})
        return result

    async def get_device_info(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self.device.to_dict()

    async def start_recording(self, _payload: dict[str, Any]) -> dict[str, Any]:
        path = await asyncio.to_thread(
            self.capture.start_recording, self.settings.snapshot_directory
        )
        result = {"recording": True, "path": str(path)}
        await self.iot.send_telemetry({"event": "recordingStarted", **result})
        return result

    async def stop_recording(self, _payload: dict[str, Any]) -> dict[str, Any]:
        path = await asyncio.to_thread(self.capture.stop_recording)
        result = {"recording": False, "path": str(path) if path else None}
        await self.iot.send_telemetry({"event": "recordingStopped", **result})
        return result

    async def set_stream_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            width = int(payload["width"])
            height = int(payload["height"])
            fps = float(payload["fps"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("width, height, and fps are required numbers") from exc
        if self.stream.running:
            raise ValueError("Stop the stream before changing its profile")
        profile = await asyncio.to_thread(
            self.capture.set_profile, width, height, fps
        )
        await self.iot.report_properties({"streamProfile": profile})
        return {"streamProfile": profile}

    async def apply_desired_properties(self, patch: dict[str, Any]) -> None:
        desired_version = patch.get("$version")
        status: dict[str, Any] = {
            "desiredVersion": desired_version,
            "status": "applied",
        }
        try:
            if "streamProfile" in patch:
                await self.set_stream_profile(patch["streamProfile"])
            if patch.get("streamEnabled") is True:
                await self.start_stream({})
            elif patch.get("streamEnabled") is False:
                await self.stop_stream({})
        except Exception as exc:
            status.update({"status": "failed", "description": str(exc)})
            LOGGER.exception("Desired properties could not be applied")
        await self.iot.report_properties({"configurationStatus": status})

    async def run(self) -> None:
        if self.settings.api_enabled:
            _start_api_server(self, self.settings.api_host, self.settings.api_port)
        if self.iot.configured:
            await self.iot.connect()
            await self.iot.report_properties(
                {
                    "camera": self.device.to_dict(),
                    "streaming": self.stream.running,
                    "status": "online",
                }
            )
        else:
            LOGGER.warning(
                "Azure IoT is not configured; running in local-only mode",
                extra={"event": "iot_not_configured"},
            )

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, stop.set)
            except NotImplementedError:
                signal.signal(signum, lambda *_: loop.call_soon_threadsafe(stop.set))

        try:
            while not stop.is_set():
                await self.iot.send_telemetry(
                    {
                        "event": "cameraHealth",
                        "cameraAvailable": True,
                        "streaming": self.stream.running,
                    }
                )
                try:
                    await asyncio.wait_for(stop.wait(), timeout=30)
                except TimeoutError:
                    pass
        finally:
            await asyncio.to_thread(self.stream.stop)
            self.capture.close()
            await self.iot.disconnect()


def _start_api_server(
    bridge: "CameraBridge", host: str, port: int
) -> threading.Thread:
    try:
        import uvicorn

        from .api import create_app

        api_app = create_app(bridge)
        config = uvicorn.Config(api_app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, name="api-server", daemon=True)
        thread.start()
        LOGGER.info(
            "Management API listening",
            extra={"event": "api_started", "port": port},
        )
        return thread
    except ImportError:
        LOGGER.warning(
            "uvicorn not installed; management API disabled",
            extra={"event": "api_disabled"},
        )
        return threading.Thread()  # no-op placeholder


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="USB/UVC camera Azure IoT bridge")
    parser.add_argument(
        "--detect-only", action="store_true", help="Print camera details and exit"
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    discovery = CameraDiscovery()
    devices = discovery.discover(settings.effective_camera_source)
    if not devices:
        LOGGER.error(
            "No compatible UVC/OpenCV video interface was found; no vendor controls were modified",
            extra={"event": "camera_not_supported"},
        )
        return 2
    device = devices[0]
    if args.detect_only:
        print(json.dumps(device.to_dict(), indent=2))
        return 0
    asyncio.run(CameraBridge(settings, device).run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())