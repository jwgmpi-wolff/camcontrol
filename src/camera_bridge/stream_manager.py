"""
Stream manager — one ffmpeg HLS rebroadcast process per camera.
Streams survive gateway restarts via auto-resume on next start_all() call.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

_HLS_ROOT = Path(__file__).parent.parent.parent / "streams" / "hls"
_HLS_ROOT.mkdir(parents=True, exist_ok=True)

# go2rtc RTSP proxy — converts Kalay P2P to RTSP for ffmpeg ingestion
_GO2RTC_RTSP_BASE = "rtsp://localhost:8554"
_GO2RTC_API = "http://localhost:1984"

_procs: dict[str, subprocess.Popen] = {}   # device_id → ffmpeg proc
_lock = threading.Lock()
_FFMPEG = shutil.which("ffmpeg")


def hls_dir(device_id: str) -> Path:
    d = _HLS_ROOT / device_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def hls_url(device_id: str, base: str = "http://localhost:8080") -> str:
    return f"{base}/streams/hls/{device_id}/live.m3u8"


def _spawn(device_id: str, source_url: str) -> subprocess.Popen:
    if not _FFMPEG:
        raise RuntimeError("ffmpeg not found — install ffmpeg and ensure it is on PATH")
    m3u8 = str(hls_dir(device_id) / "live.m3u8")
    cmd = [
        _FFMPEG, "-loglevel", "warning",
        "-re",
        "-i", source_url,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "10",
        "-hls_flags", "delete_segments+append_list",
        "-hls_segment_filename", str(hls_dir(device_id) / "seg%05d.ts"),
        m3u8,
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def start(device_id: str, source_url: str) -> dict[str, Any]:
    with _lock:
        old = _procs.pop(device_id, None)
        if old and old.poll() is None:
            old.terminate()
        proc = _spawn(device_id, source_url)
        _procs[device_id] = proc
    LOGGER.info("Stream started: %s ← %s  pid=%d", device_id, source_url, proc.pid)
    return {"device_id": device_id, "pid": proc.pid, "hls_url": hls_url(device_id), "source": source_url}


def stop(device_id: str) -> bool:
    with _lock:
        proc = _procs.pop(device_id, None)
    if proc and proc.poll() is None:
        proc.terminate()
        LOGGER.info("Stream stopped: %s", device_id)
        return True
    return False


def stop_all() -> list[str]:
    stopped = []
    with _lock:
        ids = list(_procs.keys())
    for did in ids:
        if stop(did):
            stopped.append(did)
    return stopped


def status() -> dict[str, Any]:
    result = {}
    with _lock:
        for did, proc in list(_procs.items()):
            alive = proc.poll() is None
            if not alive:
                _procs.pop(did, None)
            result[did] = {
                "pid": proc.pid,
                "alive": alive,
                "hls_url": hls_url(did),
                "hls_ready": (hls_dir(did) / "live.m3u8").exists(),
            }
    return result


def push_to_rtmp(device_id: str, rtmp_url: str) -> dict[str, Any]:
    """Push the running HLS for device_id to an RTMP endpoint (Azure / Nginx / YouTube)."""
    m3u8 = hls_dir(device_id) / "live.m3u8"
    if not m3u8.exists():
        raise RuntimeError(f"HLS not ready for {device_id} — call start() first")
    if not _FFMPEG:
        raise RuntimeError("ffmpeg not found")
    cmd = [
        _FFMPEG, "-loglevel", "error", "-re",
        "-i", str(m3u8),
        "-c", "copy", "-f", "flv", rtmp_url,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    cdn_key = f"{device_id}__cdn"
    with _lock:
        old = _procs.pop(cdn_key, None)
        if old and old.poll() is None:
            old.terminate()
        _procs[cdn_key] = proc
    LOGGER.info("CDN push started: %s → %s  pid=%d", device_id, rtmp_url, proc.pid)
    return {"device_id": device_id, "rtmp_url": rtmp_url, "pid": proc.pid}
