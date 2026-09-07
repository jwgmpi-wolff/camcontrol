"""Manual video capture: a user-triggered "start/stop recording" session.

There's no video encoder in the gateway (no ffmpeg dependency), so a
"recording" here is a burst of individual JPEG frames saved to storage at a
fixed interval while active -- the same approach motion.py uses for its
motion-triggered bursts, just started/stopped manually instead of by a frame
diff.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from .capture.base import CaptureBackend, CaptureError
from .storage.base import StorageBackend, StorageError


class RecordingSession:
    def __init__(
        self,
        camera_id: str,
        backend: CaptureBackend,
        storage: StorageBackend,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._camera_id = camera_id
        self._backend = backend
        self._storage = storage
        self._poll_interval = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.active = False
        self.session_id: str | None = None

    def start(self) -> bool:
        if self._thread is not None:
            return False
        self._stop_event.clear()
        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.active = True
        self._thread = threading.Thread(
            target=self._run, name=f"record-{self._camera_id}", daemon=True
        )
        self._thread.start()
        return True

    def stop(self) -> bool:
        if self._thread is None:
            return False
        self._stop_event.set()
        self._thread.join(timeout=5)
        self._thread = None
        self.active = False
        return True

    def _run(self) -> None:
        index = 0
        while not self._stop_event.is_set():
            try:
                frame = self._backend.get_snapshot()
                key = (
                    f"{self._camera_id}/manual/{self.session_id}/"
                    f"frame_{index:04d}.jpg"
                )
                self._storage.save(key, frame)
                index += 1
            except (CaptureError, StorageError):
                pass
            self._stop_event.wait(self._poll_interval)
