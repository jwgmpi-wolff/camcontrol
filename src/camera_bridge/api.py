"""FastAPI gateway: multi-camera snapshot + storage-provider routing."""

from __future__ import annotations

import os
import time
import hashlib
import hmac
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Header, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import DEFAULT_USERS_PATH, TokenManager, UserStore
from .camera_provision import (
    CameraProvisionError,
    CameraProvisioner,
    CameraProvisionSettings,
    redact_config,
)
from .capture.base import CaptureBackend, CaptureError
from .capture.media_browser import MediaBrowser, MediaFile, guess_media_type
from .capture.registry import build_capture_backend
from .config import DEFAULT_CONFIG_PATH, load_config, save_config
from .discovery import DiscoveredCamera, scan_network
from .h264_snapshot import H264DecodeError, decode_h264_to_jpeg
from .live_view_publisher import LiveViewPublisher
from .models import AppConfig, CameraConfig, Hi3518eSshCameraConfig, StorageConfig
from .motion import MotionWatcher
from .recording import RecordingSession
from .storage.base import StorageBackend, StorageError
from .storage.registry import build_storage_backend
from .voice_message import (
    MAX_VOICE_MESSAGE_BYTES,
    VoiceMessageError,
    VoiceMessagePlayer,
)

app = FastAPI(title="CamControl Gateway")


def _gateway_api_key() -> str:
    return os.environ.get("CAMCONTROL_API_KEY") or os.environ.get("API_KEY", "")


def _complete_jpeg(payload: bytes) -> bytes:
    """Repair camera JPEG streams that omit the terminal EOI marker."""
    if payload.startswith(b"\xff\xd8") and not payload.endswith(b"\xff\xd9"):
        return payload + b"\xff\xd9"
    return payload


class _GatewayState:
    def __init__(self) -> None:
        self.config_path = DEFAULT_CONFIG_PATH
        self.config: AppConfig = load_config(self.config_path)
        self._capture_backends: dict[str, CaptureBackend] = {}
        self._storage_backend: StorageBackend | None = None
        self._motion_watchers: dict[str, MotionWatcher] = {}
        self._recording_sessions: dict[str, RecordingSession] = {}
        self._live_view_publishers: dict[str, LiveViewPublisher] = {}
        self.camera_announcements: dict[str, dict] = {}
        self.pushed_snapshots: dict[str, bytes] = {}
        self.users = UserStore(DEFAULT_USERS_PATH)
        self.tokens = TokenManager()

    def capture_backend_for(self, camera_id: str) -> CaptureBackend:
        backend = self._capture_backends.get(camera_id)
        if backend is not None:
            return backend
        for camera in self.config.cameras:
            if camera.id == camera_id:
                backend = build_capture_backend(camera)
                self._capture_backends[camera_id] = backend
                return backend
        raise HTTPException(status_code=404, detail=f"Unknown camera id: {camera_id}")

    def storage_backend(self) -> StorageBackend:
        if self._storage_backend is None:
            self._storage_backend = build_storage_backend(self.config.storage)
        return self._storage_backend

    def recording_session_for(self, camera_id: str) -> RecordingSession:
        session = self._recording_sessions.get(camera_id)
        if session is None:
            session = RecordingSession(
                camera_id=camera_id,
                backend=self.capture_backend_for(camera_id),
                storage=self.storage_backend(),
            )
            self._recording_sessions[camera_id] = session
        return session

    def start_motion_watchers(self) -> None:
        for camera in self.config.cameras:
            if not camera.motion.enabled:
                continue
            watcher = MotionWatcher(
                camera_id=camera.id,
                config=camera.motion,
                backend=self.capture_backend_for(camera.id),
                storage=self.storage_backend(),
            )
            watcher.start()
            self._motion_watchers[camera.id] = watcher

    def stop_motion_watchers(self) -> None:
        for watcher in self._motion_watchers.values():
            watcher.stop()
        self._motion_watchers.clear()

    def start_live_view_publishers(self) -> None:
        for camera in self.config.cameras:
            if not isinstance(camera, Hi3518eSshCameraConfig):
                continue
            if not camera.live_view.enabled:
                continue
            publisher = LiveViewPublisher(
                camera_id=camera.id,
                config=camera,
                backend=self.capture_backend_for(camera.id),
                poll_interval_seconds=camera.live_view.poll_interval_seconds,
            )
            publisher.start()
            self._live_view_publishers[camera.id] = publisher

    def stop_live_view_publishers(self) -> None:
        for publisher in self._live_view_publishers.values():
            publisher.stop()
        self._live_view_publishers.clear()

    def reload(self, config: AppConfig) -> None:
        self.stop_motion_watchers()
        self.stop_live_view_publishers()
        for session in self._recording_sessions.values():
            session.stop()
        self._recording_sessions.clear()
        self.config = config
        self._capture_backends.clear()
        self._storage_backend = None
        save_config(config, self.config_path)
        self.start_motion_watchers()
        self.start_live_view_publishers()


state = _GatewayState()


@app.on_event("startup")
def _start_motion_watchers() -> None:
    state.start_motion_watchers()
    state.start_live_view_publishers()


@app.on_event("shutdown")
def _stop_motion_watchers() -> None:
    state.stop_motion_watchers()
    state.stop_live_view_publishers()


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Legacy admin gate (env-configured shared secret). Used only for
    user-management endpoints, not for video/image access."""
    expected = _gateway_api_key()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _require_auth(
    entra_principal_id: str | None = Header(
        default=None, alias="X-MS-CLIENT-PRINCIPAL-ID"
    ),
    entra_principal_name: str | None = Header(
        default=None, alias="X-MS-CLIENT-PRINCIPAL-NAME"
    ),
    x_api_key: str | None = Header(default=None),
) -> str:
    """Trust the principal injected after App Service validates an Entra token."""
    if os.environ.get("WEBSITE_INSTANCE_ID") and entra_principal_id:
        return entra_principal_name or entra_principal_id
    expected = _gateway_api_key()
    if expected and x_api_key == expected:
        return "api_key"
    raise HTTPException(status_code=401, detail="Invalid or missing credentials")


def _require_camera_key(camera_id: str, camera_key: str | None) -> None:
    master_key = _gateway_api_key()
    expected = hmac.new(
        master_key.encode(), camera_id.encode(), hashlib.sha256
    ).hexdigest()
    if not master_key or not camera_key or not hmac.compare_digest(camera_key, expected):
        raise HTTPException(status_code=401, detail="Invalid camera credentials")


class CameraSummary(BaseModel):
    id: str
    name: str
    type: str


class CaptureResult(BaseModel):
    camera_id: str
    location: str
    timestamp: str


class MotionStatus(BaseModel):
    camera_id: str
    enabled: bool
    threshold: float
    last_score: float
    motion_active: bool


class RecordingStatus(BaseModel):
    camera_id: str
    active: bool
    session_id: str | None


class LiveViewStatus(BaseModel):
    camera_id: str
    enabled: bool
    last_push_ok: bool
    url: str | None


class VoiceMessageStatus(BaseModel):
    camera_id: str
    played: bool


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str


class CreateUserRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    if not state.users.verify(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return LoginResponse(token=state.tokens.issue(body.username))


@app.post("/api/auth/users")
def add_user(body: CreateUserRequest, _: None = Depends(_require_api_key)) -> dict:
    """Add/replace a user. Gated by the admin API_KEY, not by login tokens."""
    try:
        state.users.add_user(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "username": body.username}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "cameras": len(state.config.cameras)}


@app.get("/api/cameras", response_model=list[CameraSummary])
def list_cameras(_: str = Depends(_require_auth)) -> list[CameraSummary]:
    return [
        CameraSummary(id=c.id, name=c.name, type=c.type) for c in state.config.cameras
    ]


@app.get("/api/cameras/{camera_id}/motion", response_model=MotionStatus)
def get_motion_status(camera_id: str, _: str = Depends(_require_auth)) -> MotionStatus:
    for camera in state.config.cameras:
        if camera.id == camera_id:
            watcher = state._motion_watchers.get(camera_id)
            return MotionStatus(
                camera_id=camera_id,
                enabled=camera.motion.enabled,
                threshold=camera.motion.threshold,
                last_score=watcher.last_score if watcher else 0.0,
                motion_active=watcher.motion_active if watcher else False,
            )
    raise HTTPException(status_code=404, detail=f"Unknown camera id: {camera_id}")


@app.get("/api/cameras/{camera_id}/live_view", response_model=LiveViewStatus)
def get_live_view_status(
    camera_id: str, _: str = Depends(_require_auth)
) -> LiveViewStatus:
    for camera in state.config.cameras:
        if camera.id != camera_id or not isinstance(camera, Hi3518eSshCameraConfig):
            continue
        publisher = state._live_view_publishers.get(camera_id)
        host = camera.live_view.public_url.strip() or camera.host
        for prefix in ("http://", "https://"):
            if host.startswith(prefix):
                host = host[len(prefix) :]
        host = host.rstrip("/")
        url = f"http://{host}/live.html" if camera.live_view.enabled else None
        return LiveViewStatus(
            camera_id=camera_id,
            enabled=camera.live_view.enabled,
            last_push_ok=publisher.last_push_ok if publisher else False,
            url=url,
        )
    raise HTTPException(status_code=404, detail=f"Unknown camera id: {camera_id}")


@app.get("/api/discover", response_model=list[DiscoveredCamera])
async def discover_cameras(_: str = Depends(_require_auth)) -> list[DiscoveredCamera]:
    """Scan the gateway host's own LAN subnet for candidate cameras."""
    return await scan_network()


@app.get("/api/cameras/{camera_id}/snapshot")
def get_snapshot(camera_id: str, _: str = Depends(_require_auth)) -> Response:
    pushed = state.pushed_snapshots.get(camera_id)
    if pushed is not None:
        return Response(content=pushed, media_type="image/jpeg")
    backend = state.capture_backend_for(camera_id)
    try:
        jpeg = backend.get_snapshot()
    except CaptureError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=jpeg, media_type="image/jpeg")


@app.post("/api/cameras/{camera_id}/push-snapshot")
async def push_snapshot(
    camera_id: str,
    request: Request,
    x_camera_key: str | None = Header(default=None),
) -> dict:
    """Accept a camera-originated H.264 preview buffer over HTTPS.

    This supports cameras on private home LANs: they establish the outbound
    connection, so Azure never needs to route to their RFC1918 address.
    """
    _require_camera_key(camera_id, x_camera_key)
    state.capture_backend_for(camera_id)  # validates the configured camera ID
    payload = await request.body()
    if not payload or len(payload) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Invalid snapshot payload")
    if payload.startswith(b"\xff\xd8"):
        state.pushed_snapshots[camera_id] = _complete_jpeg(payload)
    else:
        try:
            state.pushed_snapshots[camera_id] = decode_h264_to_jpeg(payload)
        except H264DecodeError as exc:
            raise HTTPException(status_code=422, detail="No decodable camera frame") from exc
    return {"status": "ok"}


@app.post("/api/cameras/{camera_id}/capture", response_model=CaptureResult)
def capture_and_store(
    camera_id: str, _: str = Depends(_require_auth)
) -> CaptureResult:
    backend = state.capture_backend_for(camera_id)
    try:
        jpeg = backend.get_snapshot()
    except CaptureError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    ts = datetime.now(timezone.utc)
    key = f"{camera_id}/{ts:%Y/%m/%d}/{int(time.time() * 1000)}.jpg"
    try:
        location = state.storage_backend().save(key, jpeg)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return CaptureResult(camera_id=camera_id, location=location, timestamp=ts.isoformat())


@app.post(
    "/api/cameras/{camera_id}/voice-message", response_model=VoiceMessageStatus
)
async def play_voice_message(
    camera_id: str, request: Request, _: str = Depends(_require_auth)
) -> VoiceMessageStatus:
    camera = next((c for c in state.config.cameras if c.id == camera_id), None)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera id: {camera_id}")
    if not isinstance(camera, Hi3518eSshCameraConfig):
        raise HTTPException(
            status_code=400, detail="Voice messages require a Hi3518e SSH camera"
        )

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_VOICE_MESSAGE_BYTES:
        raise HTTPException(status_code=413, detail="Voice message exceeds the 5 MB limit")
    audio = await request.body()
    if len(audio) > MAX_VOICE_MESSAGE_BYTES:
        raise HTTPException(status_code=413, detail="Voice message exceeds the 5 MB limit")

    try:
        VoiceMessagePlayer(camera).play(audio)
    except VoiceMessageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return VoiceMessageStatus(camera_id=camera_id, played=True)


@app.post("/api/cameras/{camera_id}/record/start", response_model=RecordingStatus)
def start_recording(
    camera_id: str, _: str = Depends(_require_auth)
) -> RecordingStatus:
    state.capture_backend_for(camera_id)  # validates camera_id exists
    session = state.recording_session_for(camera_id)
    session.start()
    return RecordingStatus(
        camera_id=camera_id, active=session.active, session_id=session.session_id
    )


@app.post("/api/cameras/{camera_id}/record/stop", response_model=RecordingStatus)
def stop_recording(
    camera_id: str, _: str = Depends(_require_auth)
) -> RecordingStatus:
    state.capture_backend_for(camera_id)  # validates camera_id exists
    session = state.recording_session_for(camera_id)
    session.stop()
    return RecordingStatus(
        camera_id=camera_id, active=session.active, session_id=session.session_id
    )


@app.get("/api/cameras/{camera_id}/record/status", response_model=RecordingStatus)
def recording_status(
    camera_id: str, _: str = Depends(_require_auth)
) -> RecordingStatus:
    state.capture_backend_for(camera_id)  # validates camera_id exists
    session = state.recording_session_for(camera_id)
    return RecordingStatus(
        camera_id=camera_id, active=session.active, session_id=session.session_id
    )


@app.get("/api/cameras/{camera_id}/media", response_model=list[MediaFile])
def list_media(camera_id: str, _: str = Depends(_require_auth)) -> list[MediaFile]:
    backend = state.capture_backend_for(camera_id)
    if not isinstance(backend, MediaBrowser):
        raise HTTPException(
            status_code=404,
            detail=f"Camera {camera_id!r} does not support media browsing",
        )
    try:
        return backend.list_media()
    except CaptureError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/cameras/{camera_id}/media/download")
def download_media(
    camera_id: str, path: str, _: str = Depends(_require_auth)
) -> StreamingResponse:
    backend = state.capture_backend_for(camera_id)
    if not isinstance(backend, MediaBrowser):
        raise HTTPException(
            status_code=404,
            detail=f"Camera {camera_id!r} does not support media browsing",
        )
    media_type = guess_media_type(path)
    content_type = {"image": "image/jpeg", "video": "video/mp4"}.get(
        media_type, "application/octet-stream"
    )
    try:
        chunks = backend.read_media(path)
    except CaptureError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return StreamingResponse(chunks, media_type=content_type)


@app.get("/api/config")
def get_config(_: str = Depends(_require_auth)) -> dict:
    dumped = state.config.model_dump()
    for camera in dumped.get("cameras", []):
        if "password" in camera:
            camera["password"] = "***" if camera["password"] else ""
    storage = dumped.get("storage", {})
    for secret_field in ("secret_key", "access_key", "password", "connection_string"):
        if secret_field in storage and storage[secret_field]:
            storage[secret_field] = "***"
    return dumped


@app.put("/api/config/cameras")
def set_cameras(
    cameras: list[CameraConfig], _: str = Depends(_require_auth)
) -> dict:
    new_config = state.config.model_copy(update={"cameras": cameras})
    state.reload(new_config)
    return {"status": "ok", "cameras": len(cameras)}


@app.put("/api/config/storage")
def set_storage(storage: StorageConfig, _: str = Depends(_require_auth)) -> dict:
    new_config = state.config.model_copy(update={"storage": storage})
    state.reload(new_config)
    return {"status": "ok", "provider": storage.provider}


class CameraAnnouncement(BaseModel):
    camera_id: str
    address: str = ""
    ssh_port: int | None = None


def _ssh_camera_or_404(camera_id: str) -> Hi3518eSshCameraConfig:
    camera = next((c for c in state.config.cameras if c.id == camera_id), None)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera id: {camera_id}")
    if not isinstance(camera, Hi3518eSshCameraConfig):
        raise HTTPException(
            status_code=400, detail="Provisioning requires a Hi3518e SSH camera"
        )
    return camera


@app.post("/api/cameras/announce")
def announce_camera(
    body: CameraAnnouncement,
    x_camera_key: str | None = Header(default=None),
) -> dict:
    """Boot-time check-in from a camera running the on-camera package.

    This is the only camera-to-gateway call in the system; it lets a camera
    that moved (new DHCP lease, new SSH port) be reached without the gateway
    having to rediscover it.
    """
    _require_camera_key(body.camera_id, x_camera_key)
    camera = _ssh_camera_or_404(body.camera_id)
    state.camera_announcements[body.camera_id] = {
        "address": body.address,
        "ssh_port": body.ssh_port,
        "seen_at": datetime.now(timezone.utc).isoformat(),
    }

    updated = False
    if body.address and body.address != camera.host:
        camera.host = body.address
        updated = True
    if body.ssh_port and body.ssh_port != camera.port:
        camera.port = body.ssh_port
        updated = True
    if updated:
        state.reload(state.config)
    return {"status": "ok", "updated": updated}


@app.get("/api/cameras/{camera_id}/provision")
def get_camera_provisioning(
    camera_id: str, _: None = Depends(_require_api_key)
) -> dict:
    """Capability probe plus the camera's stored settings, secrets redacted."""
    camera = _ssh_camera_or_404(camera_id)
    provisioner = CameraProvisioner(camera)
    try:
        capabilities = provisioner.probe()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    settings: dict[str, str] = {}
    if capabilities.package_installed:
        try:
            settings = redact_config(provisioner.read_config())
        except CameraProvisionError:
            settings = {}

    return {
        "camera_id": camera_id,
        "installed": capabilities.package_installed,
        "wifi_interface": capabilities.wifi_interface,
        "tools": capabilities.tools,
        "can_host_ap": capabilities.can_host_ap,
        "can_serve_portal": capabilities.can_serve_portal,
        "boot_hook_candidates": list(capabilities.boot_hook_candidates),
        "issues": capabilities.blocking_issues,
        "settings": settings,
        "last_announcement": state.camera_announcements.get(camera_id),
    }


@app.post("/api/cameras/{camera_id}/provision/install")
def install_camera_package(
    camera_id: str, _: None = Depends(_require_api_key)
) -> dict:
    camera = _ssh_camera_or_404(camera_id)
    try:
        log = CameraProvisioner(camera).install()
    except CameraProvisionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok", "log": log}


@app.put("/api/cameras/{camera_id}/provision/config")
def set_camera_provisioning(
    camera_id: str,
    settings: CameraProvisionSettings,
    reboot: bool = False,
    _: None = Depends(_require_api_key),
) -> dict:
    """Writes settings to the camera. They take effect on the next reboot."""
    camera = _ssh_camera_or_404(camera_id)
    provisioner = CameraProvisioner(camera)
    try:
        merged = provisioner.write_config(settings)
        if reboot:
            provisioner.reboot()
    except CameraProvisionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "status": "ok",
        "rebooting": reboot,
        "settings": redact_config(merged),
    }


@app.post("/api/cameras/{camera_id}/provision/reboot")
def reboot_camera(camera_id: str, _: None = Depends(_require_api_key)) -> dict:
    camera = _ssh_camera_or_404(camera_id)
    try:
        CameraProvisioner(camera).reboot()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok", "rebooting": True}
