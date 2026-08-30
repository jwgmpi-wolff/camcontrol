"""
Stream router: directs a confirmed RTSP stream to one or more destinations.
Destinations: Windows dashboard (MJPEG relay), Android backend relay,
local disk, NAS/SMB path, or Azure Blob Storage.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class StreamDestination:
    kind: str          # "mjpeg_relay" | "local" | "nas" | "azure"
    path: str          # file path, SMB path, or Azure container name
    enabled: bool = True


@dataclass
class StreamSession:
    rtsp_url: str
    destinations: list[StreamDestination]
    active: bool = False
    _thread: threading.Thread | None = field(default=None, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _latest_frame: bytes | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get_latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_frame


class StreamRouter:
    def __init__(self) -> None:
        self._sessions: dict[str, StreamSession] = {}

    def start(self, session_id: str, rtsp_url: str, destinations: list[StreamDestination]) -> None:
        if session_id in self._sessions and self._sessions[session_id].active:
            LOGGER.warning("Session %s already active", session_id)
            return

        session = StreamSession(rtsp_url=rtsp_url, destinations=destinations)
        self._sessions[session_id] = session
        session.active = True
        session._stop.clear()

        thread = threading.Thread(
            target=self._capture_loop,
            args=(session,),
            daemon=True,
            name=f"stream-{session_id}",
        )
        session._thread = thread
        thread.start()
        LOGGER.info("Stream session started: %s", session_id)

    def stop(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        session._stop.set()
        if session._thread:
            session._thread.join(timeout=5)
        session.active = False
        LOGGER.info("Stream session stopped: %s", session_id)

    def get_frame(self, session_id: str) -> bytes | None:
        session = self._sessions.get(session_id)
        return session.get_latest_jpeg() if session else None

    def _capture_loop(self, session: StreamSession) -> None:
        cap = cv2.VideoCapture(session.rtsp_url, cv2.CAP_ANY)
        if not cap.isOpened():
            LOGGER.error("Cannot open RTSP stream: %s", _redact(session.rtsp_url))
            session.active = False
            return

        while not session._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                LOGGER.warning("Frame read failed; reconnecting in 2 s")
                cap.release()
                session._stop.wait(2)
                cap = cv2.VideoCapture(session.rtsp_url, cv2.CAP_ANY)
                continue

            # Encode to JPEG for relay consumers
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            jpeg = buf.tobytes()
            with session._lock:
                session._latest_frame = jpeg

            # Fan out to recording destinations
            for dest in session.destinations:
                if not dest.enabled:
                    continue
                if dest.kind == "local":
                    _write_frame_to_file(frame, dest.path)
                # NAS and Azure handled by FFmpegRecorder and BlobStorageClient respectively

        cap.release()

    def active_sessions(self) -> list[str]:
        return [sid for sid, s in self._sessions.items() if s.active]


def _redact(url: str) -> str:
    import re
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", url)


def _write_frame_to_file(frame: Any, directory: str) -> None:
    from datetime import UTC, datetime
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = Path(directory) / f"frame-{ts}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), frame)
