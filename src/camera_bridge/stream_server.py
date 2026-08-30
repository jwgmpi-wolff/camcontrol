"""Authenticated local RTSP endpoint backed by GStreamer on Linux."""

from __future__ import annotations

import base64
import logging
import platform
import threading
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)


class StreamServerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StreamEndpoint:
    protocol: str
    port: int
    path: str
    authentication: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "protocol": self.protocol,
            "port": self.port,
            "path": self.path,
            "authentication": self.authentication,
        }


class StreamServer:
    def __init__(
        self,
        device_path: str,
        protocol: str,
        port: int,
        username: str | None,
        password: str | None,
    ) -> None:
        self.device_path = device_path
        self.protocol = protocol
        self.port = port
        self.username = username
        self.password = password
        self._server: object | None = None
        self._loop: object | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> StreamEndpoint:
        if self.running:
            return self.endpoint()
        if self.protocol == "webrtc":
            raise StreamServerError(
                "WebRTC signaling is not bundled; deploy a TLS signaling service and TURN "
                "relay, then integrate it at this boundary"
            )
        if self.protocol != "rtsp":
            raise StreamServerError(f"Unsupported stream protocol: {self.protocol}")
        if platform.system() != "Linux":
            raise StreamServerError(
                "The bundled RTSP server is supported only on Linux edge gateways"
            )
        if not self.username or not self.password:
            raise StreamServerError("RTSP authentication credentials are required")

        try:
            import gi

            gi.require_version("Gst", "1.0")
            gi.require_version("GstRtspServer", "1.0")
            from gi.repository import GLib, Gst, GstRtspServer
        except (ImportError, ValueError) as exc:
            raise StreamServerError(
                "GStreamer RTSP bindings are unavailable; install the documented Linux "
                "packages or use the supplied container"
            ) from exc

        Gst.init(None)
        server = GstRtspServer.RTSPServer.new()
        server.set_service(str(self.port))
        factory = GstRtspServer.RTSPMediaFactory.new()
        factory.set_shared(True)
        factory.set_launch(
            f'( v4l2src device="{self.device_path}" ! videoconvert ! '
            "x264enc tune=zerolatency speed-preset=veryfast bitrate=1500 ! "
            "rtph264pay name=pay0 pt=96 config-interval=1 )"
        )

        role = "camera-viewer"
        factory.add_role(
            role,
            "media.factory.access",
            True,
            "media.factory.construct",
            True,
        )
        auth = GstRtspServer.RTSPAuth.new()
        token = GstRtspServer.RTSPToken.new(
            GstRtspServer.RTSP_TOKEN_MEDIA_FACTORY_ROLE,
            GLib.Variant("s", role),
        )
        basic = base64.b64encode(
            f"{self.username}:{self.password}".encode("utf-8")
        ).decode("ascii")
        auth.add_basic(basic, token)
        server.set_auth(auth)
        server.get_mount_points().add_factory("/camera", factory)

        loop = GLib.MainLoop.new(None, False)
        if server.attach(None) == 0:
            raise StreamServerError("Failed to attach the RTSP server")
        thread = threading.Thread(target=loop.run, name="rtsp-server", daemon=True)
        thread.start()
        self._server = server
        self._loop = loop
        self._thread = thread
        LOGGER.info("RTSP stream started", extra={"event": "stream_started"})
        return self.endpoint()

    def stop(self) -> None:
        if self._loop:
            self._loop.quit()
        if self._thread:
            self._thread.join(timeout=5)
        self._server = None
        self._loop = None
        self._thread = None
        LOGGER.info("Stream stopped", extra={"event": "stream_stopped"})

    def endpoint(self) -> StreamEndpoint:
        return StreamEndpoint("rtsp", self.port, "/camera", "basic")
