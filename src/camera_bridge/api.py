"""FastAPI REST + MJPEG frame API consumed by the Flutter management UI."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from .main import CameraBridge

LOGGER = logging.getLogger(__name__)

_bridge: "CameraBridge | None" = None


def _require_key(x_api_key: str | None = Header(default=None)) -> None:
    key = _bridge.settings.api_key if _bridge else None
    if key and x_api_key != key:
        raise HTTPException(401, "Invalid or missing X-API-Key header")


def create_app(bridge: "CameraBridge") -> FastAPI:
    global _bridge
    _bridge = bridge

    if not bridge.settings.api_key:
        LOGGER.warning(
            "API_KEY is not set; management API is unprotected on the local network",
            extra={"event": "api_no_auth"},
        )

    app = FastAPI(title="Camera Bridge", version="1.0", docs_url="/api/docs")
    app.add_middleware(
        CORSMiddleware,
        # TODO: restrict allow_origins to known UI origins before public deployment
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["*"],
    )

    # Serve dashboard at root so it loads from the same origin as the API (no CORS issues)
    _dashboard = Path(__file__).parent.parent.parent / "camera-platform" / "dashboard.html"
    _static = Path(__file__).parent.parent.parent / "camera-platform" / "static"
    if _static.exists():
        app.mount("/static", StaticFiles(directory=str(_static)), name="static")
        # SW must be served from root scope for PWA install on Android
        from fastapi.responses import FileResponse as _FR
        @app.get("/sw.js")
        async def service_worker() -> _FR:
            return _FR(str(_static / "sw.js"), media_type="application/javascript")
    if _dashboard.exists():
        from fastapi.responses import FileResponse
        @app.get("/")
        async def dashboard() -> FileResponse:
            return FileResponse(str(_dashboard), media_type="text/html")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "streaming": _bridge.stream.running if _bridge else False,
            "recording": _bridge.capture.recording if _bridge else False,
            "rtspUrl": _bridge.settings.effective_camera_source if _bridge else None,
        }

    @app.put("/api/camera/rtsp-url", dependencies=[Depends(_require_key)])
    async def set_rtsp_url(body: dict[str, Any]) -> dict[str, Any]:
        """Hot-swap the RTSP URL without restarting the process."""
        if not _bridge:
            raise HTTPException(503, "Bridge not initialised")
        url = body.get("url", "").strip()
        if not url.startswith(("rtsp://", "rtsps://", "0", "/dev/")):
            raise HTTPException(400, "url must be an RTSP URL or device path")
        _bridge.capture.close()
        _bridge.capture.device_path = url
        _bridge.stream.device_path = url
        import os
        os.environ["RTSP_URL"] = url
        return {"rtspUrl": url, "status": "applied"}

    @app.get("/api/camera/rtsp-probe")
    async def rtsp_probe(ip: str, port: int = 554, path: str = "/ch0_0.h264") -> dict[str, Any]:
        """Quick reachability check for an RTSP URL — no auth bypass, no brute-force."""
        import asyncio
        url = f"rtsp://{ip}:{port}{path}"
        try:
            def _check() -> bool:
                cap = cv2.VideoCapture(url, cv2.CAP_ANY)
                # 5-second open timeout instead of the 30-second default
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
                opened = cap.isOpened()
                cap.release()
                return opened
            opened = await asyncio.wait_for(asyncio.to_thread(_check), timeout=7.0)
            return {"url": url, "reachable": opened}
        except Exception as exc:
            return {"url": url, "reachable": False, "error": str(exc)}

    @app.get("/api/device", dependencies=[Depends(_require_key)])
    async def device_info() -> dict[str, Any]:
        if not _bridge:
            raise HTTPException(503, "Bridge not initialised")
        return _bridge.device.to_dict()

    @app.post("/api/snapshot", dependencies=[Depends(_require_key)])
    async def snapshot() -> dict[str, Any]:
        if not _bridge:
            raise HTTPException(503)
        return await _bridge.capture_snapshot({})

    @app.get("/api/stream/frame")
    async def frame(x_api_key: str | None = Header(default=None)) -> Response:
        """Single JPEG frame; polled by Flutter live-view at ~10 fps."""
        _require_key(x_api_key)
        if not _bridge:
            raise HTTPException(503, "Bridge not initialised")
        src = _bridge.settings.effective_camera_source
        # Block PC webcam (index 0) — require an explicit RTSP URL
        if not src.startswith(("rtsp://", "rtsps://", "/dev/")):
            raise HTTPException(503, "No RTSP camera configured. Use WiFi Camera Setup.")
        try:
            import asyncio

            raw = await asyncio.to_thread(_bridge.capture.read_frame)
            _, buf = cv2.imencode(".jpg", raw, [cv2.IMWRITE_JPEG_QUALITY, 75])
            return Response(content=buf.tobytes(), media_type="image/jpeg")
        except Exception as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/api/camera/onvif-probe")
    async def onvif_probe(ip: str, port: int = 8000) -> dict[str, Any]:
        """ONVIF GetCapabilities SOAP probe — returns RTSP port hint if found."""
        import re, urllib.request
        soap = (
            '<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
            '<s:Body><GetCapabilities xmlns="http://www.onvif.org/ver10/device/wsdl">'
            "<Category>All</Category></GetCapabilities></s:Body></s:Envelope>"
        )
        hdrs = {"Content-Type": "application/soap+xml; charset=utf-8",
                "SOAPAction": '"http://www.onvif.org/ver10/device/wsdl/GetCapabilities"'}
        try:
            req = urllib.request.Request(
                f"http://{ip}:{port}/onvif/device_service",
                data=soap.encode(), headers=hdrs, method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read(4096).decode(errors="replace")
            m = re.search(r"(\d{1,5})</(?:[^:]+:)?RtspPort>", body, re.IGNORECASE)
            rtsp_port = int(m.group(1)) if m else None
            return {"ip": ip, "port": port, "onvif": True, "rtspPort": rtsp_port, "snippet": body[:600]}
        except Exception as exc:
            return {"ip": ip, "port": port, "onvif": False, "error": str(exc)}

    @app.get("/api/camera/qr-connect")
    async def qr_connect_image(camera_ip: str = "10.0.0.161", rtsp_port: int = 554) -> Response:
        """Return a PNG QR code encoding the gateway + camera connection JSON."""
        import io, json, socket
        try:
            import qrcode
        except ImportError:
            raise HTTPException(503, "qrcode package not installed")

        def _local_ip() -> str:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("10.0.0.1", 1))
                return s.getsockname()[0]
            finally:
                s.close()

        gw_ip = _local_ip()
        payload = json.dumps(
            {
                "gateway": f"http://{gw_ip}:8080",
                "camera": camera_ip,
                "cameraPort": 8000,
                "model": "YI-YHS3017",
                "rtsp": f"rtsp://{camera_ip}/ch0_0.h264",
            },
            separators=(",", ":"),
        )
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4
        )
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")

    @app.get("/api/camera/yi-snapshot")
    async def yi_snapshot(ip: str = "10.0.0.161") -> Response:
        """Pull a JPEG snapshot directly from the YI camera's port 8000 binary protocol."""
        import asyncio
        from .yi_protocol import YICameraClient

        async def _get() -> bytes | None:
            client = YICameraClient(ip)
            return await asyncio.to_thread(client.capture_jpeg, 10.0)

        try:
            jpg = await asyncio.wait_for(_get(), timeout=12.0)
            if jpg:
                return Response(content=jpg, media_type="image/jpeg")
            return Response(content=b"", status_code=503,
                            headers={"X-YI-Error": "no frame from port 8000"})
        except Exception as exc:
            return Response(content=str(exc).encode(), status_code=503)

    # ── YI Cloud API endpoints (no YI app required after login) ─────────────

    @app.post("/api/cloud/login")
    async def cloud_login(body: dict[str, Any]) -> dict[str, Any]:
        """Login to YI cloud. Accepts google_token (preferred) or email+password (legacy)."""
        from .yi_cloud import login, login_google
        google_token = body.get("google_token", "").strip()
        if google_token:
            result = await asyncio.to_thread(login_google, google_token)
        else:
            email = body.get("email", "").strip()
            password = body.get("password", "")
            if not email or not password:
                raise HTTPException(400, "google_token or (email + password) required")
            result = await asyncio.to_thread(login, email, password)
        if not result.get("ok"):
            raise HTTPException(401, result.get("error", "Login failed"))
        return {"ok": True, "user_id": result.get("user_id")}

    @app.post("/api/cloud/inject-session")
    async def inject_session(body: dict[str, Any]) -> dict[str, Any]:
        """Directly inject a captured YI session token and HMAC (from HTTP Toolkit HAR)."""
        from .yi_cloud import _session
        import time
        token = body.get("token", "").strip()
        user_id = body.get("user_id", "")
        hmac_val = body.get("hmac", "")
        if not token and not hmac_val:
            raise HTTPException(400, "token or hmac required")
        _session.update({"token": token, "user_id": user_id, "hmac": hmac_val,
                          "login_at": time.time(), "base": "https://us.laikuai.com"})
        return {"ok": True, "injected": True, "user_id": user_id}

    @app.post("/api/cloud/google-auth-start")
    async def google_auth_start() -> dict[str, Any]:
        """Return the Google OAuth URL for the user to visit, and start the callback listener."""
        from .yi_cloud import get_google_token_url, capture_google_token_via_browser
        url = get_google_token_url()
        asyncio.create_task(asyncio.to_thread(capture_google_token_via_browser))
        return {
            "auth_url": url,
            "callback": "http://localhost:8765/oauth/callback",
            "note": "Browser opened automatically. After Google sign-in, token captured and login attempted.",
        }

    @app.post("/api/cloud/google-login")
    async def google_login_direct(body: dict[str, Any]) -> dict[str, Any]:
        """Exchange a Google id_token directly for a YI session. Paste token from browser devtools."""
        from .yi_cloud import login_google
        token = body.get("google_token", "").strip()
        if not token:
            raise HTTPException(400, "google_token required")
        result = await asyncio.to_thread(login_google, token)
        if not result.get("ok"):
            raise HTTPException(401, result.get("error", "Google token exchange failed"))
        return {"ok": True, "user_id": result.get("user_id")}

    @app.get("/api/cloud/status")
    async def cloud_status() -> dict[str, Any]:
        from .yi_cloud import status
        return status()

    @app.get("/api/cloud/devices")
    async def cloud_devices() -> dict[str, Any]:
        import asyncio
        from .yi_cloud import get_devices, status
        if not status().get("authenticated"):
            raise HTTPException(401, "Not logged in. Call POST /api/cloud/login first.")
        devices = await asyncio.to_thread(get_devices)
        return {"devices": devices, "count": len(devices)}

    @app.get("/api/cloud/stream")
    async def cloud_stream(device_id: str) -> dict[str, Any]:
        """Get live stream URL for a camera via YI cloud."""
        import asyncio
        from .yi_cloud import get_stream_url, status
        if not status().get("authenticated"):
            raise HTTPException(401, "Not logged in.")
        result = await asyncio.to_thread(get_stream_url, device_id)
        if result.get("ok") and result.get("url"):
            # Hot-apply RTSP URL if it's RTSP
            url = result["url"]
            if url.startswith(("rtsp://", "rtsps://")):
                if _bridge:
                    _bridge.capture.device_path = url
                    _bridge.stream.device_path = url
                    import os; os.environ["RTSP_URL"] = url
                result["applied"] = True
        return result

    @app.get("/api/cloud/snapshot")
    async def cloud_snapshot(device_id: str) -> Response:
        """Get a JPEG snapshot from camera via YI cloud."""
        import asyncio
        from .yi_cloud import get_snapshot, status
        if not status().get("authenticated"):
            raise HTTPException(401, "Not logged in.")
        jpg = await asyncio.to_thread(get_snapshot, device_id)
        if jpg:
            return Response(content=jpg, media_type="image/jpeg")
        raise HTTPException(503, "Snapshot unavailable")

    @app.get("/api/camera/yi-probe")
    async def yi_probe(ip: str = "10.0.0.248") -> dict[str, Any]:
        """Test raw connection to YI camera port 8000 and attempt token exchange."""
        import asyncio, socket, struct
        MAGIC = 0x55AA55AA
        MSG_TOKEN_REQ = 0x000003E8

        def _probe() -> dict:
            s = socket.socket()
            s.settimeout(5)
            try:
                s.connect((ip, 8000))
                # Send token request
                pkt = struct.pack(">IIII", MAGIC, MSG_TOKEN_REQ, 0, 0)
                s.sendall(pkt)
                s.settimeout(3)
                try:
                    data = s.recv(512)
                    if len(data) >= 16:
                        magic, msg_type, token, length = struct.unpack(">IIII", data[:16])
                        return {"connected": True, "magic": hex(magic),
                                "msg_type": hex(msg_type), "token": token,
                                "payload_len": length, "raw": data[:64].hex()}
                    return {"connected": True, "raw": data.hex(), "note": "short response"}
                except socket.timeout:
                    return {"connected": True, "note": "no response to token request"}
            except Exception as e:
                return {"connected": False, "error": str(e)}
            finally:
                s.close()

        result = await asyncio.to_thread(_probe)
        result["ip"] = ip
        return result

    @app.get("/api/camera/qr-bindkey")
    async def qr_get_bindkey() -> dict[str, Any]:
        """Get a fresh binding key from YI cloud for QR camera pairing."""
        from .yi_cloud import _session, _curl_request, _base
        uid = _session.get("user_id", "")
        hmac_val = _session.get("hmac", "")
        if not uid:
            raise HTTPException(401, "Not logged in — inject session first")
        import time, urllib.parse
        ts = str(int(time.time() * 1000))
        # Exact URL pattern from live capture: hmac + userid + seq + timestamp
        hmac_enc = urllib.parse.quote(hmac_val, safe="") if hmac_val else ""
        url = (f"{_base()}/v2/qrcode/get_bindkey"
               f"?hmac={hmac_enc}&userid={uid}&seq=1&timestamp={ts}")
        resp = _curl_request("GET", url)
        if resp.get("code") == "20000":
            return {"ok": True, "bindkey": resp["data"]["bindkey"]}
        raise HTTPException(502, f"YI API error: {resp}")

    @app.get("/api/camera/qr-check")
    async def qr_check_bindkey(bindkey: str) -> dict[str, Any]:
        """Poll YI cloud to check if camera scanned the QR (ret=1 = success)."""
        from .yi_cloud import _session, _curl_request, _base
        uid = _session.get("user_id", "")
        hmac_val = _session.get("hmac", "")
        import time, urllib.parse
        ts = str(int(time.time() * 1000))
        hmac_enc = urllib.parse.quote(hmac_val, safe="") if hmac_val else ""
        url = (f"{_base()}/v2/qrcode/check_bindkey"
               f"?hmac={hmac_enc}&seq=1&bindkey={bindkey}&timestamp={ts}&userid={uid}")
        resp = _curl_request("GET", url)
        if resp.get("code") == "20000":
            data = resp.get("data", {})
            return {"ok": True, "scanned": data.get("ret", 0) == 1,
                    "uid": data.get("uid", ""), "raw": data}
        return {"ok": False, "error": resp}

    @app.post("/api/camera/register-qr")
    async def register_qr(body: dict[str, Any]) -> dict[str, Any]:
        """Parse a YI camera QR string and locate the camera on the local subnet."""
        import asyncio, base64, ipaddress, socket
        from urllib.parse import parse_qs

        raw = body.get("qr", "").strip()
        if not raw:
            raise HTTPException(400, "qr field required")

        # Parse b=...&s=base64(ssid)&p=obfuscated_password
        params = dict(kv.split("=", 1) for kv in raw.split("&") if "=" in kv)
        try:
            ssid = base64.b64decode(params["s"] + "==").decode("utf-8", errors="replace")
        except Exception:
            ssid = "(unreadable)"

        hint_ip: str | None = body.get("ip")  # optional caller-supplied IP

        def _tcp_open(ip: str, port: int, timeout: float = 0.8) -> bool:
            s = socket.socket()
            s.settimeout(timeout)
            ok = s.connect_ex((ip, port)) == 0
            s.close()
            return ok

        # If caller supplied an IP hint, trust it; otherwise scan /24 for port 8000
        found_ip: str | None = None
        if hint_ip:
            found_ip = hint_ip if _tcp_open(hint_ip, 8000) else None
        else:
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
                net = ipaddress.IPv4Interface(f"{local_ip}/24").network
                candidates = [str(h) for h in net.hosts()]
            except Exception:
                candidates = [f"10.0.0.{i}" for i in range(1, 255)]

            async def _scan_one(ip: str) -> str | None:
                ok = await asyncio.to_thread(_tcp_open, ip, 8000, 0.6)
                return ip if ok else None

            results = await asyncio.gather(*(_scan_one(ip) for ip in candidates))
            hits = [r for r in results if r]
            found_ip = hits[0] if hits else None

        registration = {
            "ssid": ssid,
            "cameraIp": found_ip,
            "port": 8000,
            "rtspCandidates": (
                [
                    f"rtsp://{found_ip}/ch0_0.h264",
                    f"rtsp://{found_ip}/ch0_1.h264",
                    f"rtsp://{found_ip}/ch0_0.h264",  # alias
                ]
                if found_ip
                else []
            ),
            "note": (
                "Camera found on local network."
                if found_ip
                else "Camera not found — ensure it is on the same subnet."
            ),
        }

        # Hot-apply first RTSP candidate if bridge is available
        if found_ip and _bridge:
            candidate = registration["rtspCandidates"][0]
            _bridge.capture.device_path = candidate
            _bridge.stream.device_path = candidate
            import os
            os.environ["RTSP_URL"] = candidate
            registration["rtspApplied"] = candidate

        return registration

    # ── Stream rebroadcast + multi-camera registry ────────────────────────────

    from . import stream_manager, registry as cam_registry

    _streams_root = Path(__file__).parent.parent.parent / "streams"
    _streams_root.mkdir(parents=True, exist_ok=True)
    app.mount("/streams", StaticFiles(directory=str(_streams_root)), name="streams")

    @app.get("/api/cameras")
    async def list_cameras() -> dict[str, Any]:
        cams = cam_registry.list_cameras()
        st = stream_manager.status()
        for c in cams:
            c["stream"] = st.get(c.get("device_id", ""), {"alive": False, "hls_ready": False})
        return {"cameras": cams, "count": len(cams)}

    @app.post("/api/cameras/import")
    async def import_cameras() -> dict[str, Any]:
        """Pull all cameras from YI cloud and save to local registry."""
        from .yi_cloud import get_devices, status as yi_status
        if not yi_status().get("authenticated"):
            raise HTTPException(401, "Not logged in — call POST /api/cloud/login first")
        devices = await asyncio.to_thread(get_devices)
        imported = cam_registry.import_from_yi_devices(devices)
        return {"imported": len(imported), "cameras": imported}

    @app.post("/api/cameras/add")
    async def add_camera(body: dict[str, Any]) -> dict[str, Any]:
        did = body.get("device_id", "").strip()
        if not did:
            raise HTTPException(400, "device_id required")
        record = cam_registry.upsert_camera(did, {k: v for k, v in body.items() if k != "device_id"})
        return {"ok": True, "camera": record}

    @app.delete("/api/cameras/{device_id}")
    async def delete_camera(device_id: str) -> dict[str, Any]:
        stream_manager.stop(device_id)
        removed = cam_registry.remove_camera(device_id)
        return {"ok": removed, "device_id": device_id}

    @app.post("/api/stream/start")
    async def stream_start(body: dict[str, Any]) -> dict[str, Any]:
        from .yi_cloud import get_stream_url, status as yi_status
        from . import stream_manager
        device_id = body.get("device_id", "")
        source_url = body.get("source_url", "")
        if not device_id:
            raise HTTPException(400, "device_id required")
        if not source_url:
            # Check if go2rtc has this camera as a named stream (Kalay -> RTSP)
            cam = cam_registry.get_camera(device_id)
            if cam and cam.get("kalay_did"):
                # Stream name: use the camera name slug or device_id slug
                slug = (cam.get("name") or device_id).lower().replace(" ", "_").replace("-", "_")
                source_url = f"{stream_manager._GO2RTC_RTSP_BASE}/{slug}"
            elif yi_status().get("authenticated"):
                result = await asyncio.to_thread(get_stream_url, device_id)
                source_url = result.get("url", "")
            if not source_url:
                raise HTTPException(503, "No source_url and go2rtc/cloud auth not available")
        try:
            info = await asyncio.to_thread(stream_manager.start, device_id, source_url)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))
        cam_registry.upsert_camera(device_id, {"last_source_url": source_url})
        return {"ok": True, **info}

    @app.post("/api/stream/start-all")
    async def stream_start_all() -> dict[str, Any]:
        """Start HLS for every registered camera."""
        from .yi_cloud import get_stream_url, status as yi_status
        cams = cam_registry.list_cameras()
        results = []
        for cam in cams:
            did = cam.get("device_id", "")
            source_url = cam.get("last_source_url", "")
            if not source_url and yi_status().get("authenticated"):
                r = await asyncio.to_thread(get_stream_url, did)
                source_url = r.get("url", "")
                if source_url:
                    cam_registry.upsert_camera(did, {"last_source_url": source_url})
            if source_url:
                try:
                    info = await asyncio.to_thread(stream_manager.start, did, source_url)
                    results.append({"device_id": did, "ok": True, **info})
                except Exception as exc:
                    results.append({"device_id": did, "ok": False, "error": str(exc)})
            else:
                results.append({"device_id": did, "ok": False, "error": "no source URL"})
        return {"started": sum(1 for r in results if r["ok"]), "results": results}

    @app.post("/api/stream/start-phone")
    async def stream_start_phone(body: dict[str, Any]) -> dict[str, Any]:
        """Stream phone screen via scrcpy (Windows named pipe) → ffmpeg → HLS."""
        import subprocess as _sp, threading as _th, tempfile as _tmp
        device_id = body.get("device_id", "phone_screen")
        ffmpeg_bin = shutil.which("ffmpeg")
        scrcpy_bin = shutil.which("scrcpy")
        if not ffmpeg_bin:
            raise HTTPException(503, "ffmpeg not found")
        if not scrcpy_bin:
            raise HTTPException(503, "scrcpy not found")

        out_dir = stream_manager._HLS_ROOT / device_id
        out_dir.mkdir(parents=True, exist_ok=True)
        m3u8 = str(out_dir / "live.m3u8")
        # Use a temp file as buffer since scrcpy 4.x doesn't support stdout piping
        buf_file = str(out_dir / "scrcpy_buf.mkv")

        def _run():
            """Loop: scrcpy records 2-min chunks → ffmpeg appends to HLS."""
            seg_n = 0
            while True:
                # scrcpy records to buffer file (120s max, then loops)
                sc = _sp.Popen(
                    [scrcpy_bin, "--no-audio", "--video-codec=h264",
                     f"--record={buf_file}", "--time-limit=120"],
                    stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
                )
                sc.wait()
                # ffmpeg processes the recorded chunk and appends to HLS
                if Path(buf_file).exists() and Path(buf_file).stat().st_size > 10000:
                    ff = _sp.Popen([
                        ffmpeg_bin, "-loglevel", "error", "-i", buf_file,
                        "-c:v", "copy", "-f", "hls",
                        "-hls_time", "2", "-hls_list_size", "10",
                        "-hls_flags", "append_list+delete_segments",
                        "-hls_segment_filename", str(out_dir / f"seg%05d.ts"),
                        m3u8,
                    ], stdout=_sp.DEVNULL, stderr=_sp.PIPE)
                    stream_manager._procs[device_id] = ff
                    ff.wait()
                    try: Path(buf_file).unlink()
                    except: pass

        t = _th.Thread(target=_run, daemon=True)
        t.start()

        await asyncio.sleep(1)
        cam_registry.upsert_camera(device_id, {"name": "Phone Screen (YI app)", "last_source_url": "scrcpy://screen"})
        return {"ok": True, "device_id": device_id, "pid": 0,
                "hls_url": stream_manager.hls_url(device_id), "source": "scrcpy-loop",
                "note": "HLS appears after first 2-minute scrcpy chunk. Keep phone YI app on camera view."}

    @app.post("/api/stream/stop")
    async def stream_stop(body: dict[str, Any]) -> dict[str, Any]:
        device_id = body.get("device_id", "")
        ok = await asyncio.to_thread(stream_manager.stop, device_id)
        return {"ok": ok, "stopped": device_id}

    @app.post("/api/stream/stop-all")
    async def stream_stop_all() -> dict[str, Any]:
        stopped = await asyncio.to_thread(stream_manager.stop_all)
        return {"stopped": stopped}

    @app.get("/api/stream/status")
    async def stream_status() -> dict[str, Any]:
        st = stream_manager.status()
        return {"active_streams": st, "count": len(st)}

    @app.post("/api/stream/push-cdn")
    async def stream_push_cdn(body: dict[str, Any]) -> dict[str, Any]:
        """Push camera HLS to RTMP (Azure / Nginx / YouTube)."""
        device_id = body.get("device_id", "")
        rtmp_url = body.get("rtmp_url", "")
        if not device_id or not rtmp_url:
            raise HTTPException(400, "device_id and rtmp_url required")
        try:
            info = await asyncio.to_thread(stream_manager.push_to_rtmp, device_id, rtmp_url)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))
        return {"ok": True, **info}

    @app.post("/api/recording/start", dependencies=[Depends(_require_key)])
    async def start_recording() -> dict[str, Any]:
        if not _bridge:
            raise HTTPException(503)
        return await _bridge.start_recording({})

    @app.post("/api/recording/stop", dependencies=[Depends(_require_key)])
    async def stop_recording() -> dict[str, Any]:
        if not _bridge:
            raise HTTPException(503)
        return await _bridge.stop_recording({})

    @app.get("/api/recordings", dependencies=[Depends(_require_key)])
    async def list_recordings() -> dict[str, Any]:
        if not _bridge:
            raise HTTPException(503)
        directory = _bridge.settings.snapshot_directory
        files = sorted(
            directory.glob("recording-*.avi"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return {
            "recordings": [
                {"name": f.name, "bytes": f.stat().st_size} for f in files[:50]
            ]
        }

    return app
