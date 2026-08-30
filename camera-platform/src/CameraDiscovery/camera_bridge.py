"""
YI Camera Bridge — production IoT bridge for any confirmed RTSP stream.

Works with any camera exposing a standard RTSP endpoint on your local network.
Set RTSP_URL to a URL you own and have confirmed reachable.

DOES NOT: flash firmware, bypass auth, use default credentials, or modify camera software.

Run:
    pip install azure-iot-device opencv-python-headless python-dotenv
    cp .env.example .env   # set RTSP_URL and IOTHUB_DEVICE_CONNECTION_STRING
    python camera_bridge.py
"""

import json
import logging
import os
import re
import signal
import sys
import time
from pathlib import Path

import cv2
from azure.iot.device import IoTHubDeviceClient, Message, MethodResponse
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s [%(levelname)s] %(message)s")

# Config from environment only — never hardcoded
IOTHUB_CONNECTION_STRING = os.getenv("IOTHUB_DEVICE_CONNECTION_STRING")
RTSP_URL             = os.getenv("RTSP_URL")
SNAPSHOT_DIR         = Path(os.getenv("SNAPSHOT_DIR", "./data/snapshots"))
TELEMETRY_INTERVAL_S = int(os.getenv("TELEMETRY_INTERVAL_SECONDS", "30"))


class YICameraBridge:
    def __init__(self, connection_string: str | None, rtsp_url: str) -> None:
        self.rtsp_url = rtsp_url
        self.is_streaming = False
        self.cap: cv2.VideoCapture | None = None
        self._shutdown = False
        if connection_string:
            self.client: IoTHubDeviceClient | None = \
                IoTHubDeviceClient.create_from_connection_string(connection_string)
        else:
            logging.warning("IOTHUB_DEVICE_CONNECTION_STRING not set; telemetry disabled")
            self.client = None

    def start(self) -> None:
        if self.client:
            logging.info("Connecting to Azure IoT Hub...")
            self.client.connect()
            self.client.on_method_request_received = self.method_request_handler
            logging.info("Azure IoT Device Client active and listening for direct methods.")

    def method_request_handler(self, method_request: object) -> None:
        name: str = method_request.name  # type: ignore[attr-defined]
        logging.info("Command received: %s", name)

        if name == "startStream":
            self.is_streaming = True
            payload = {"status": "SUCCESS", "message": f"Streaming from {_redact(self.rtsp_url)}"}
            status = 200
        elif name == "stopStream":
            self.is_streaming = False
            if self.cap:
                self.cap.release()
                self.cap = None
            payload = {"status": "SUCCESS", "message": "Stream stopped."}
            status = 200
        elif name == "captureSnapshot":
            path = self.take_snapshot()
            payload = ({"status": "SUCCESS", "file": path} if path
                       else {"status": "ERROR", "message": "Failed to capture frame."})
            status = 200 if path else 500
        elif name == "getDeviceStatus":
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_ANY)
            online = cap.isOpened(); cap.release()
            payload = {"status": "SUCCESS", "cameraOnline": online,
                       "streaming": self.is_streaming, "rtspEndpoint": _redact(self.rtsp_url)}
            status = 200
        elif name == "setRecordingDestination":
            dest = (getattr(method_request, "payload", None) or {}).get("destination", "")
            if dest not in {"local", "nas", "azure"}:
                payload = {"status": "ERROR", "message": "destination must be local|nas|azure"}
                status = 400
            else:
                logging.info("Recording destination -> %s", dest)
                payload = {"status": "SUCCESS", "recordingDestination": dest}
                status = 200
        elif name == "setStreamDestination":
            dest = (getattr(method_request, "payload", None) or {}).get("destination", "")
            logging.info("Stream destination -> %s", dest)
            payload = {"status": "SUCCESS", "streamDestination": dest}
            status = 200
        else:
            payload = {"status": "ERROR", "message": f"Method not recognized: {name}"}
            status = 404

        if self.client:
            resp = MethodResponse.create_from_method_request(
                method_request, status, payload)  # type: ignore[arg-type]
            self.client.send_method_response(resp)

    def take_snapshot(self) -> str | None:
        cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_ANY)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return None
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        filename = str(SNAPSHOT_DIR / f"snapshot_{int(time.time())}.jpg")
        cv2.imwrite(filename, frame)
        logging.info("Snapshot saved: %s", filename)
        return filename

    def run_telemetry_loop(self) -> None:
        logging.info("Starting telemetry loop every %d s", TELEMETRY_INTERVAL_S)
        while not self._shutdown:
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_ANY)
            is_alive = cap.isOpened()
            cap.release()
            telemetry = {
                "deviceId": "YHS.3017_Outdoor",
                "cameraOnline": is_alive,
                "streaming": self.is_streaming,
                "rtspEndpoint": _redact(self.rtsp_url),
                "timestamp": time.time(),
            }
            logging.info("Publishing Telemetry to Azure: %s", telemetry)
            if self.client:
                msg = Message(json.dumps(telemetry))
                msg.content_type = "application/json"
                msg.content_encoding = "utf-8"
                self.client.send_message(msg)
            time.sleep(TELEMETRY_INTERVAL_S)

    def shutdown(self) -> None:
        self._shutdown = True
        if self.cap:
            self.cap.release()
        if self.client:
            self.client.disconnect()


def _redact(url: str) -> str:
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", url)


if __name__ == "__main__":
    if not RTSP_URL:
        logging.error("RTSP_URL is not set. Run camera discovery first.")
        sys.exit(1)
    bridge = YICameraBridge(IOTHUB_CONNECTION_STRING, RTSP_URL)
    signal.signal(signal.SIGINT,  lambda *_: bridge.shutdown())
    signal.signal(signal.SIGTERM, lambda *_: bridge.shutdown())
    bridge.start()
    bridge.run_telemetry_loop()