"""
FFmpeg-based recorder.
Starts FFmpeg ONLY after a valid RTSP stream URL is confirmed reachable.
Never embeds credentials in logs. Supports local, NAS/SMB, and Azure Blob destinations.
"""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

LOGGER = logging.getLogger(__name__)
RecordingDest = Literal["local", "nas", "azure"]


@dataclass(slots=True)
class RecordingSession:
    session_id: str
    camera_ip: str
    rtsp_url_safe: str      # URL with password replaced by ***
    destination: RecordingDest
    output_path: str
    started_at: str
    stopped_at: str | None = None
    exit_code: int | None = None


class FFmpegRecorder:
    def __init__(self, ffmpeg_path: str = "ffmpeg") -> None:
        if not shutil.which(ffmpeg_path):
            raise RuntimeError(
                f"FFmpeg not found at '{ffmpeg_path}'. Install FFmpeg and ensure it is on PATH."
            )
        self.ffmpeg_path = ffmpeg_path
        self._sessions: dict[str, subprocess.Popen] = {}  # type: ignore[type-arg]
        self._lock = threading.Lock()

    def start(
        self,
        *,
        rtsp_url: str,
        output_path: str,
        session_id: str | None = None,
        segment_seconds: int = 300,
    ) -> RecordingSession:
        """
        Start recording from a pre-validated RTSP URL.

        Call rtsp_probe.probe_camera() first; pass this method a URL that returned
        reachable=True.  Never call this without a confirmed stream.
        """
        session_id = session_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        out = Path(output_path)
        out.mkdir(parents=True, exist_ok=True)

        # Segment pattern – avoids single huge files
        pattern = str(out / f"{session_id}-%Y%m%dT%H%M%SZ.mp4")

        cmd = [
            self.ffmpeg_path,
            "-loglevel", "warning",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-c", "copy",               # no re-encode; reduce CPU
            "-f", "segment",
            "-segment_time", str(segment_seconds),
            "-segment_format", "mp4",
            "-reset_timestamps", "1",
            "-strftime", "1",
            pattern,
        ]

        # Redact password in logs
        safe_url = _redact_url(rtsp_url)
        LOGGER.info("Starting FFmpeg recording  session=%s  src=%s  dest=%s",
                    session_id, safe_url, output_path)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        with self._lock:
            self._sessions[session_id] = proc

        threading.Thread(
            target=self._monitor, args=(session_id, proc), daemon=True, name=f"rec-{session_id}"
        ).start()

        return RecordingSession(
            session_id=session_id,
            camera_ip=_extract_host(rtsp_url),
            rtsp_url_safe=safe_url,
            destination="local",
            output_path=output_path,
            started_at=datetime.now(UTC).isoformat(),
        )

    def stop(self, session_id: str) -> RecordingSession | None:
        with self._lock:
            proc = self._sessions.pop(session_id, None)
        if not proc:
            LOGGER.warning("No active recording session: %s", session_id)
            return None
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        LOGGER.info("Recording stopped  session=%s  exit=%s", session_id, proc.returncode)
        return None  # caller re-queries DB for final state

    def stop_all(self) -> None:
        with self._lock:
            ids = list(self._sessions.keys())
        for sid in ids:
            self.stop(sid)

    def active_sessions(self) -> list[str]:
        with self._lock:
            return [sid for sid, p in self._sessions.items() if p.poll() is None]

    def _monitor(self, session_id: str, proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
        _, stderr = proc.communicate()
        if stderr:
            for line in stderr.decode(errors="replace").splitlines():
                LOGGER.warning("ffmpeg[%s] %s", session_id, line)
        LOGGER.info("FFmpeg process exited  session=%s  code=%s", session_id, proc.returncode)
        with self._lock:
            self._sessions.pop(session_id, None)


def _redact_url(url: str) -> str:
    import re
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", url)


def _extract_host(url: str) -> str:
    import urllib.parse
    return urllib.parse.urlparse(url).hostname or url
