"""Tests for H.264-to-JPEG snapshot decoding via ffmpeg.

/tmp/view on this camera firmware turned out to be a raw H.264 elementary
stream ring buffer, not JPEG (see h264_snapshot.py's module docstring for
how that was confirmed). These tests generate a real, self-contained H.264
clip with ffmpeg itself, then verify decode_h264_to_jpeg can pull a still
frame out of it -- exercising the actual subprocess/pipe codepath, not just
a mock.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from camera_bridge.h264_snapshot import (
    H264DecodeError,
    decode_h264_to_jpeg,
    ffmpeg_available,
)

pytestmark = pytest.mark.skipif(
    not ffmpeg_available(), reason="ffmpeg is not installed on this machine"
)


def _generate_test_h264_clip() -> bytes:
    """A tiny synthetic H.264 elementary stream (no container), generated
    entirely by ffmpeg's testsrc filter -- no external fixture files needed."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=5:duration=1",
            "-c:v",
            "libx264",
            "-f",
            "h264",
            "pipe:1",
        ],
        capture_output=True,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    assert proc.stdout
    return proc.stdout


def test_decode_h264_to_jpeg_produces_valid_jpeg():
    h264_data = _generate_test_h264_clip()

    jpeg = decode_h264_to_jpeg(h264_data)

    assert jpeg.startswith(b"\xff\xd8")
    assert jpeg.endswith(b"\xff\xd9")


def test_decode_h264_to_jpeg_raises_on_garbage_input():
    with pytest.raises(H264DecodeError):
        decode_h264_to_jpeg(b"not any kind of video data" * 100)


def test_decode_h264_to_jpeg_raises_on_empty_input():
    with pytest.raises(H264DecodeError):
        decode_h264_to_jpeg(b"")


def test_ffmpeg_available_reflects_real_path_lookup():
    assert ffmpeg_available() == (shutil.which("ffmpeg") is not None)
