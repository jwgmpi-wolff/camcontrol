"""Gateway-side motion detection: polls a capture backend's snapshots and
diffs consecutive frames itself, independent of the camera's own (often
unreliable, unconfigurable) built-in motion detection.

On a detected change, records a burst of snapshots to the storage backend
for `record_seconds`, then enters a cooldown before it can trigger again.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from datetime import datetime, timezone

from PIL import Image, ImageChops

from .capture.base import CaptureBackend, CaptureError
from .models import MotionConfig
from .storage.base import StorageBackend, StorageError

logger = logging.getLogger(__name__)

# Downsample before diffing: keeps the comparison cheap and reduces noise
# from JPEG recompression artifacts between polls.
_DIFF_SIZE = (160, 90)


def frame_diff_score(prev: bytes, curr: bytes) -> float:
    """Mean per-pixel grayscale difference (0-255) between two JPEG frames."""
    prev_img = Image.open(io.BytesIO(prev)).convert("L").resize(_DIFF_SIZE)
    curr_img = Image.open(io.BytesIO(curr)).convert("L").resize(_DIFF_SIZE)
    diff = ImageChops.difference(prev_img, curr_img)
    histogram = diff.histogram()
    total_pixels = sum(histogram)
    if total_pixels == 0:
        return 0.0
    weighted_sum = sum(value * count for value, count in enumerate(histogram))
    return weighted_sum / total_pixels


class MotionWatcher:
    """Runs a per-camera poll/diff/record loop on a dedicated thread."""

    def __init__(
        self,
        camera_id: str,
        config: MotionConfig,
        backend: CaptureBackend,
        storage: StorageBackend,
    ) -> None:
        self._camera_id = camera_id
        self._config = config
        self._backend = backend
        self._storage = storage
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_score: float = 0.0
        self.motion_active: bool = False

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name=f"motion-{self._camera_id}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        cfg = self._config
        prev_frame: bytes | None = None
        cooldown_until = 0.0

        while not self._stop_event.is_set():
            loop_start = time.monotonic()
            try:
                frame = self._backend.get_snapshot()
            except CaptureError as exc:
                logger.warning("motion[%s]: snapshot failed: %s", self._camera_id, exc)
                self._stop_event.wait(cfg.poll_interval_seconds)
                continue

            if prev_frame is not None:
                try:
                    self.last_score = frame_diff_score(prev_frame, frame)
                except Exception:  # noqa: BLE001 - bad/partial JPEG, skip this pair
                    self.last_score = 0.0
                if (
                    self.last_score >= cfg.threshold
                    and loop_start >= cooldown_until
                ):
                    self._record_burst(frame)
                    cooldown_until = time.monotonic() + cfg.cooldown_seconds

            prev_frame = frame
            elapsed = time.monotonic() - loop_start
            self._stop_event.wait(max(0.0, cfg.poll_interval_seconds - elapsed))

    def _record_burst(self, first_frame: bytes) -> None:
        self.motion_active = True
        logger.info(
            "motion[%s]: triggered (score=%.1f >= %.1f)",
            self._camera_id,
            self.last_score,
            self._config.threshold,
        )
        started = datetime.now(timezone.utc)
        event_id = f"{started:%Y%m%d_%H%M%S}"
        deadline = time.monotonic() + self._config.record_seconds
        frame = first_frame
        index = 0
        try:
            while True:
                key = f"{self._camera_id}/motion/{event_id}/frame_{index:04d}.jpg"
                try:
                    self._storage.save(key, frame)
                except StorageError as exc:
                    logger.warning(
                        "motion[%s]: failed to save %s: %s", self._camera_id, key, exc
                    )
                index += 1
                if time.monotonic() >= deadline or self._stop_event.is_set():
                    break
                self._stop_event.wait(self._config.poll_interval_seconds)
                try:
                    frame = self._backend.get_snapshot()
                except CaptureError as exc:
                    logger.warning(
                        "motion[%s]: snapshot failed mid-burst: %s",
                        self._camera_id,
                        exc,
                    )
                    break
        finally:
            self.motion_active = False
