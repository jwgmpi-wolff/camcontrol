"""
YI Camera binary protocol client for port 8000.

Protocol (reverse-engineered from community research):
  - TCP connect to port 8000
  - Exchange: client sends token request, camera responds with session token
  - Authenticate with token
  - Request video stream (H.264 frames)
  - Frames arrive as tagged binary packets

Packet structure (community-documented):
  [4-byte magic] [4-byte msg_type] [4-byte length] [payload...]
"""
from __future__ import annotations

import socket
import struct
import threading
import time
import logging
from typing import Callable

LOGGER = logging.getLogger(__name__)

# Known message type IDs from community reverse engineering
MSG_TOKEN_REQ    = 0x000003E8   # 1000 - client requests session token
MSG_TOKEN_RESP   = 0x000003E9   # 1001 - camera returns token
MSG_START_STREAM = 0x000003EE   # 1006 - start video stream
MSG_STOP_STREAM  = 0x000003EF   # 1007 - stop video stream
MSG_VIDEO_FRAME  = 0x00000001   # 1    - H.264 video frame
MSG_AUDIO_FRAME  = 0x00000002   # 2    - audio frame
MSG_PING         = 0x00000006   # 6    - keepalive ping
MSG_PONG         = 0x00000007   # 7    - keepalive pong

# Magic bytes that prefix every packet
MAGIC = 0x55AA55AA


class YICameraClient:
    """Connects to a YI camera's port 8000 and pulls H.264 video frames."""

    def __init__(self, host: str, port: int = 8000, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._token: int = 0
        self._running = False
        self._recv_thread: threading.Thread | None = None
        self.on_frame: Callable[[bytes], None] | None = None  # called with raw H.264 NAL units

    # ── Connection ──────────────────────────────────────────────────────────

    def connect(self) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            LOGGER.info("Connected to %s:%d", self.host, self.port)
            return True
        except Exception as exc:
            LOGGER.error("Connection failed: %s", exc)
            self._sock = None
            return False

    def disconnect(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    # ── Packet framing ───────────────────────────────────────────────────────

    def _build_packet(self, msg_type: int, payload: bytes = b"") -> bytes:
        header = struct.pack(">IIII", MAGIC, msg_type, self._token, len(payload))
        return header + payload

    def _send(self, msg_type: int, payload: bytes = b"") -> None:
        if not self._sock:
            raise RuntimeError("Not connected")
        pkt = self._build_packet(msg_type, payload)
        self._sock.sendall(pkt)
        LOGGER.debug("Sent msg_type=0x%08X len=%d", msg_type, len(payload))

    def _recv_packet(self) -> tuple[int, int, bytes]:
        """Read one packet: returns (msg_type, token, payload)."""
        assert self._sock
        header = self._recv_exact(16)
        magic, msg_type, token, length = struct.unpack(">IIII", header)
        if magic != MAGIC:
            # Some firmware uses a different magic — try reading as raw length
            LOGGER.warning("Unexpected magic: 0x%08X", magic)
        payload = self._recv_exact(length) if length > 0 else b""
        LOGGER.debug("Recv msg_type=0x%08X token=%d len=%d", msg_type, token, length)
        return msg_type, token, payload

    def _recv_exact(self, n: int) -> bytes:
        assert self._sock
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Camera closed connection")
            buf += chunk
        return buf

    # ── Protocol handshake ───────────────────────────────────────────────────

    def authenticate(self) -> bool:
        """Perform token exchange with the camera."""
        try:
            # Step 1: send token request with token=0
            self._token = 0
            self._send(MSG_TOKEN_REQ)

            # Step 2: wait for token response
            msg_type, token, payload = self._recv_packet()
            if msg_type == MSG_TOKEN_RESP:
                self._token = token
                LOGGER.info("Got session token: %d", self._token)
                return True
            else:
                LOGGER.warning("Expected token response, got 0x%08X", msg_type)
                # Some cameras skip token exchange — use token=0
                return True
        except Exception as exc:
            LOGGER.error("Auth failed: %s", exc)
            return False

    # ── Stream control ───────────────────────────────────────────────────────

    def start_video(self, channel: int = 0, quality: int = 2) -> bool:
        """Request H.264 video stream. channel=0 is high-res, channel=1 is low-res."""
        try:
            # Payload: channel (uint32) + quality (uint32)
            payload = struct.pack(">II", channel, quality)
            self._send(MSG_START_STREAM, payload)
            LOGGER.info("Requested video stream channel=%d quality=%d", channel, quality)
            return True
        except Exception as exc:
            LOGGER.error("Start stream failed: %s", exc)
            return False

    def stop_video(self) -> None:
        try:
            self._send(MSG_STOP_STREAM)
        except Exception:
            pass

    # ── Receive loop ─────────────────────────────────────────────────────────

    def start_receiving(self, on_frame: Callable[[bytes], None]) -> None:
        """Start background thread to receive video frames."""
        self.on_frame = on_frame
        self._running = True
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def _recv_loop(self) -> None:
        ping_interval = 15.0
        last_ping = time.time()
        while self._running:
            try:
                if self._sock:
                    self._sock.settimeout(2.0)
                msg_type, token, payload = self._recv_packet()

                if msg_type == MSG_VIDEO_FRAME and self.on_frame:
                    self.on_frame(payload)
                elif msg_type == MSG_AUDIO_FRAME:
                    pass  # ignore audio for now
                elif msg_type == MSG_PING:
                    self._send(MSG_PONG)

                # Send keepalive ping periodically
                now = time.time()
                if now - last_ping > ping_interval:
                    self._send(MSG_PING)
                    last_ping = now

            except socket.timeout:
                # Normal timeout — send ping
                if time.time() - last_ping > ping_interval:
                    try:
                        self._send(MSG_PING)
                        last_ping = time.time()
                    except Exception:
                        break
                continue
            except ConnectionError as exc:
                LOGGER.warning("Receive loop: %s", exc)
                break
            except Exception as exc:
                if self._running:
                    LOGGER.error("Receive loop error: %s", exc)
                break
        self._running = False
        LOGGER.info("Receive loop ended")

    # ── High-level: capture single JPEG snapshot ─────────────────────────────

    def capture_jpeg(self, timeout: float = 8.0) -> bytes | None:
        """Connect, request one H.264 keyframe, decode to JPEG, return bytes."""
        import cv2
        import numpy as np

        collected: list[bytes] = []
        done = threading.Event()

        def on_frame(data: bytes) -> None:
            collected.append(data)
            if len(collected) >= 3:   # collect a few frames for keyframe
                done.set()

        if not self.connect():
            return None
        try:
            self.authenticate()
            self.start_video(channel=0, quality=2)
            self.start_receiving(on_frame)
            done.wait(timeout=timeout)
            self.stop_video()
        finally:
            self.disconnect()

        if not collected:
            return None

        # Decode H.264 via OpenCV
        raw = b"".join(collected)
        arr = np.frombuffer(raw, dtype=np.uint8)
        cap = cv2.VideoCapture()
        # Write to temp file and decode
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".h264", delete=False) as f:
            f.write(raw)
            tmp = f.name
        try:
            vcap = cv2.VideoCapture(tmp)
            ret, frame = vcap.read()
            vcap.release()
            if ret:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                return buf.tobytes()
        finally:
            os.unlink(tmp)
        return None
