"""Publishes a periodically-refreshed live snapshot directly onto a camera's
own web server (its static-file-only lwsws instance), so a browser can view
it at http://<camera-ip>/live.html without going through the gateway at all.

The camera's web UI has no CGI/dynamic content and /tmp/view itself is not
reliably a clean single JPEG (see hi3518e_ssh.py's docstring), so this reuses
the gateway's own working capture+extraction path and pushes the result as a
plain static file (live.jpg) the camera's own httpd already knows how to
serve; live.html just polls that file on a timer.
"""

from __future__ import annotations

import logging
import threading

import paramiko

from .capture.base import CaptureBackend, CaptureError
from .models import Hi3518eSshCameraConfig

logger = logging.getLogger(__name__)

_REMOTE_WWW_DIR = "/home/yi-hack-v3/www"
_REMOTE_IMAGE_PATH = f"{_REMOTE_WWW_DIR}/live.jpg"
_REMOTE_PAGE_PATH = f"{_REMOTE_WWW_DIR}/live.html"

_LIVE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Live view</title>
<style>
  body { background:#111; margin:0; display:flex; align-items:center;
         justify-content:center; height:100vh; }
  img { max-width:100%; max-height:100vh; }
</style>
</head>
<body>
<img id="frame" src="live.jpg" alt="live view">
<script>
  var img = document.getElementById('frame');
  setInterval(function () {
    img.src = 'live.jpg?t=' + Date.now();
  }, 3000);
</script>
</body>
</html>
"""


class LiveViewPublisher:
    """Pushes fresh snapshots to a camera's own web root on a fixed interval."""

    def __init__(
        self,
        camera_id: str,
        config: Hi3518eSshCameraConfig,
        backend: CaptureBackend,
        poll_interval_seconds: float = 3.0,
    ) -> None:
        self._camera_id = camera_id
        self._config = config
        self._backend = backend
        self._poll_interval = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_push_ok = False

    def start(self) -> None:
        if self._thread is not None:
            return
        self._deploy_page()
        self._thread = threading.Thread(
            target=self._run, name=f"liveview-{self._camera_id}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self._config.host,
            port=self._config.port,
            username=self._config.username,
            password=self._config.password,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        return client

    def _deploy_page(self) -> None:
        """One-time (idempotent) upload of live.html to the camera's www dir.
        No sftp-server on this firmware, so this pipes the content through a
        shell `cat > file` over a normal exec channel, same trick already
        used for the recording watcher script."""
        try:
            client = self._connect()
            try:
                _stdin, stdout, _stderr = client.exec_command(
                    f"cat > {_REMOTE_PAGE_PATH}", timeout=10
                )
                stdout.channel.settimeout(10)
                _stdin.write(_LIVE_HTML.encode())
                _stdin.channel.shutdown_write()
                stdout.read()
            finally:
                client.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "liveview[%s]: failed to deploy live.html: %s", self._camera_id, exc
            )

    def _push_frame(self, jpeg: bytes) -> None:
        client = self._connect()
        try:
            _stdin, stdout, _stderr = client.exec_command(
                f"cat > {_REMOTE_IMAGE_PATH}", timeout=15
            )
            stdout.channel.settimeout(15)
            _stdin.write(jpeg)
            _stdin.channel.shutdown_write()
            stdout.read()
        finally:
            client.close()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                jpeg = self._backend.get_snapshot()
                self._push_frame(jpeg)
                self.last_push_ok = True
            except (CaptureError, Exception) as exc:  # noqa: BLE001
                self.last_push_ok = False
                logger.warning(
                    "liveview[%s]: push failed: %s", self._camera_id, exc
                )
            self._stop_event.wait(self._poll_interval)
