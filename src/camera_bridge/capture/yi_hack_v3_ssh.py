"""Capture backend for yi-hack-v3 firmware on Hi3518e-family YI cameras.

This firmware has no RTSP/ONVIF server, but its stock ISP pipeline keeps a
live JPEG preview frame embedded inside a fixed-size memory-mapped buffer at
/tmp/view. There is no documented offset table for it, so each pull scans the
raw bytes for a JPEG SOI/EOI pair. The file is read over an SSH exec channel
(`cat <path>`) rather than SFTP/SCP, because this firmware does not ship an
sftp-server binary.
"""

from __future__ import annotations

import posixpath
import shlex
import threading
import time
from collections.abc import Iterator

import paramiko

from ..jpeg_extract import extract_jpeg
from ..models import YiHackV3SshCameraConfig
from .base import CaptureBackend, CaptureError
from .media_browser import MediaBrowser, MediaFile, guess_media_type

# /tmp/view is a live, non-double-buffered mmap region the ISP pipeline
# overwrites in place only occasionally (observed: stable/identical content
# across repeated reads once populated, torn only during the brief write
# itself). A short retry budget rides out that write window without making
# every poll expensive; callers should treat an eventual failure as "no new
# frame yet" and keep showing the last successful frame, not a hard error.
_SNAPSHOT_RETRY_ATTEMPTS = 6
_SNAPSHOT_RETRY_DELAY_SECONDS = 0.3
_SNAPSHOT_READ_TIMEOUT_SECONDS = 20


class YiHackV3SshCapture(CaptureBackend, MediaBrowser):
    def __init__(self, config: YiHackV3SshCameraConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._client: paramiko.SSHClient | None = None

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self._config.host,
            port=self._config.port,
            username=self._config.username,
            # Pass the literal string (including "") rather than None: this
            # firmware's dropbear expects a real (possibly blank) password
            # auth attempt, not paramiko's no-password/none-auth path.
            password=self._config.password,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        return client

    def _ensure_client(self) -> paramiko.SSHClient:
        if self._client is None:
            try:
                self._client = self._connect()
            except Exception as exc:  # noqa: BLE001 - surfaced as CaptureError
                self._client = None
                raise CaptureError(
                    f"Cannot connect to {self._config.host}: {exc}"
                ) from exc
        return self._client

    def get_snapshot(self) -> bytes:
        last_error: CaptureError | None = None
        for attempt in range(_SNAPSHOT_RETRY_ATTEMPTS):
            try:
                return self._read_one_snapshot()
            except CaptureError as exc:
                last_error = exc
                if attempt < _SNAPSHOT_RETRY_ATTEMPTS - 1:
                    time.sleep(_SNAPSHOT_RETRY_DELAY_SECONDS)
        assert last_error is not None
        raise last_error

    def _read_one_snapshot(self) -> bytes:
        with self._lock:
            client = self._ensure_client()
            try:
                _stdin, stdout, stderr = client.exec_command(
                    f"cat {self._config.remote_view_path}", timeout=10
                )
                # exec_command's timeout only bounds channel setup; the
                # blocking .read() below needs its own socket timeout or it
                # can hang forever if the remote side never signals EOF.
                stdout.channel.settimeout(_SNAPSHOT_READ_TIMEOUT_SECONDS)
                data = stdout.read()
                err = stderr.read()
            except Exception as exc:  # noqa: BLE001
                self._client = None
                raise CaptureError(
                    f"Lost SSH session to {self._config.host}: {exc}"
                ) from exc

            if not data:
                raise CaptureError(
                    f"No data read from {self._config.remote_view_path} on "
                    f"{self._config.host}: {err.decode(errors='replace')}"
                )

            jpeg = extract_jpeg(data)
            if jpeg is None:
                raise CaptureError(
                    f"No JPEG frame found in {self._config.remote_view_path} "
                    f"on {self._config.host}"
                )
            return jpeg

    def list_media(self) -> list[MediaFile]:
        remote_dir = self._config.remote_media_dir
        # size<TAB>mtime_epoch<TAB>relative_path, one per line. Busybox-only
        # (no GNU find -printf, no stat), so this shells out per file.
        cmd = (
            f"cd {shlex.quote(remote_dir)} && "
            "find . -type f 2>/dev/null | while read -r f; do "
            'printf "%s\\t%s\\t%s\\n" "$(wc -c < "$f")" '
            '"$(date -r "$f" +%s 2>/dev/null || echo 0)" "$f"; done'
        )
        with self._lock:
            client = self._ensure_client()
            try:
                _stdin, stdout, stderr = client.exec_command(cmd, timeout=20)
                stdout.channel.settimeout(20)
                output = stdout.read().decode(errors="replace")
                err = stderr.read().decode(errors="replace")
            except Exception as exc:  # noqa: BLE001
                self._client = None
                raise CaptureError(
                    f"Lost SSH session to {self._config.host}: {exc}"
                ) from exc

        if err.strip() and not output.strip():
            raise CaptureError(f"Listing {remote_dir} failed: {err}")

        files: list[MediaFile] = []
        for line in output.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            size_str, mtime_str, rel_path = parts
            rel_path = rel_path[2:] if rel_path.startswith("./") else rel_path
            if not rel_path or "System Volume Information" in rel_path:
                continue
            try:
                size = int(size_str)
                mtime = int(mtime_str)
            except ValueError:
                continue
            files.append(
                MediaFile(
                    path=rel_path,
                    size=size,
                    modified_epoch=mtime,
                    media_type=guess_media_type(rel_path),
                )
            )
        return files

    def read_media(self, path: str) -> Iterator[bytes]:
        remote_dir = self._config.remote_media_dir
        normalized = posixpath.normpath(f"/{path}").lstrip("/")
        if normalized.startswith("..") or not normalized:
            raise CaptureError(f"Invalid media path: {path!r}")
        remote_path = posixpath.join(remote_dir, normalized)

        with self._lock:
            client = self._ensure_client()
            try:
                _stdin, stdout, _stderr = client.exec_command(
                    f"cat {shlex.quote(remote_path)}", timeout=60
                )
            except Exception as exc:  # noqa: BLE001
                self._client = None
                raise CaptureError(
                    f"Lost SSH session to {self._config.host}: {exc}"
                ) from exc
            channel = stdout.channel
            channel.settimeout(30)
            while True:
                try:
                    chunk = channel.recv(65536)
                except TimeoutError:
                    break
                if not chunk:
                    break
                yield chunk

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
