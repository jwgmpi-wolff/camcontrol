"""
RTSP stream URL probe for discovered cameras.

IMPORTANT:
- Requires user-supplied credentials (no default login, no brute-force).
- Only probes when port 554 is already confirmed open.
- Uses opencv-python-headless; falls back to socket-level check if unavailable.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)

RTSP_PATH_CANDIDATES = [
    "/ch0_0.h264",  # yi-hack-Allwinner-v2 YI Outdoor 1080p (h30ga/r40ga)
    "/ch0_0.h264",
    "/ch0_1.h264",
    "/live",
    "/stream1",
]


@dataclass(slots=True)
class RtspProbeResult:
    url: str
    reachable: bool
    width: int = 0
    height: int = 0
    fps: float = 0.0
    codec: str = ""
    error: str = ""


def build_rtsp_urls(
    ip: str,
    port: int = 554,
    username: str | None = None,
    password: str | None = None,
) -> list[str]:
    """Build candidate RTSP URLs with optional user credentials."""
    auth = ""
    if username and password:
        # Credentials supplied by the owner; never guessed
        import urllib.parse
        auth = f"{urllib.parse.quote(username)}:{urllib.parse.quote(password)}@"
    return [f"rtsp://{auth}{ip}:{port}{path}" for path in RTSP_PATH_CANDIDATES]


def _socket_rtsp_check(ip: str, port: int = 554, timeout_s: float = 2.0) -> bool:
    """Minimal OPTIONS handshake to confirm RTSP server presence."""
    try:
        with socket.create_connection((ip, port), timeout=timeout_s) as sock:
            request = (
                f"OPTIONS rtsp://{ip}:{port}/ RTSP/1.0\r\n"
                f"CSeq: 1\r\n"
                f"User-Agent: CameraPlatform/1.0\r\n\r\n"
            )
            sock.sendall(request.encode())
            response = sock.recv(256).decode(errors="replace")
            return "RTSP/1.0 200" in response or "RTSP/1.0 401" in response
    except OSError:
        return False


def probe_rtsp_url(
    url: str, timeout_s: float = 4.0, use_opencv: bool = True
) -> RtspProbeResult:
    """
    Probe a single RTSP URL.  Uses OpenCV if available (for capability details),
    otherwise falls back to a raw socket OPTIONS check.
    """
    if use_opencv:
        try:
            import cv2

            cap = cv2.VideoCapture(url, cv2.CAP_ANY)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_s * 1000)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = float(cap.get(cv2.CAP_PROP_FPS))
                fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
                codec = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00")
                cap.release()
                return RtspProbeResult(url=url, reachable=True, width=w, height=h, fps=fps, codec=codec)
            cap.release()
            return RtspProbeResult(url=url, reachable=False, error="Stream did not open")
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("OpenCV probe failed for %s: %s", url, exc)
            use_opencv = False

    # Socket fallback
    import urllib.parse

    parsed = urllib.parse.urlparse(url)
    reachable = _socket_rtsp_check(parsed.hostname or "", parsed.port or 554, timeout_s)
    return RtspProbeResult(
        url=url,
        reachable=reachable,
        error="" if reachable else "No RTSP 200/401 response",
    )


def probe_camera(
    ip: str,
    port: int = 554,
    username: str | None = None,
    password: str | None = None,
    timeout_s: float = 4.0,
) -> list[RtspProbeResult]:
    """Probe all RTSP candidates and return results. Port must be pre-confirmed open."""
    urls = build_rtsp_urls(ip, port, username, password)
    results = []
    for url in urls:
        safe_url = url.replace(password or "", "***") if password else url
        LOGGER.info("Probing RTSP: %s", safe_url)
        result = probe_rtsp_url(url, timeout_s=timeout_s)
        results.append(result)
        if result.reachable:
            LOGGER.info("  ✓ Reachable  %dx%d @ %.1f fps  codec=%s", result.width, result.height, result.fps, result.codec)
        else:
            LOGGER.info("  ✗ %s", result.error)
    return results
