"""Decodes a single still JPEG frame out of a raw H.264 elementary stream
buffer, via an ffmpeg subprocess.

Some Hi3518e camera firmware builds' /tmp/view "live preview" buffer (see
capture/hi3518e_ssh.py) is NOT JPEG data at all -- despite the vendor naming
and prior assumptions -- it's a raw H.264 ring buffer shared via mmap between
the ISP/encoder process and the local recording/motion-detection processes.
It has no SPS/PPS at a fixed offset (the parameter sets scroll through the
buffer along with everything else), so ffmpeg reports decode errors for most
of the buffer, but reliably still decodes at least one real frame out of it
before giving up -- which is all a single still-frame "snapshot" needs.
"""

from __future__ import annotations

import shutil
import subprocess

_FFMPEG_TIMEOUT_SECONDS = 20


class H264DecodeError(Exception):
    """Raised when ffmpeg cannot decode any frame out of the given buffer."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def decode_h264_to_jpeg(h264_data: bytes) -> bytes:
    """Feeds a raw H.264 byte buffer to ffmpeg and returns one decoded JPEG
    frame's bytes. Raises H264DecodeError if no frame could be decoded."""
    if not ffmpeg_available():
        raise H264DecodeError("ffmpeg is not installed / not on PATH")

    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "h264",
                "-i",
                "pipe:0",
                "-vframes",
                "1",
                "-f",
                "image2",
                "-c:v",
                "mjpeg",
                "pipe:1",
            ],
            input=h264_data,
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise H264DecodeError("ffmpeg timed out decoding the buffer") from exc

    # ffmpeg commonly exits non-zero here even on success: most of a raw
    # ring-buffer snippet like this is undecodable without SPS/PPS context,
    # so its own error-rate threshold trips after emitting the one frame we
    # actually wanted. Trust the presence of real JPEG output over the exit
    # code.
    if not proc.stdout or not proc.stdout.startswith(b"\xff\xd8"):
        stderr = proc.stderr.decode(errors="replace")[-500:]
        raise H264DecodeError(f"ffmpeg produced no decodable frame: {stderr}")
    return proc.stdout
