"""FastAPI gateway: multi-camera snapshot + storage-provider routing."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Header, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import DEFAULT_USERS_PATH, TokenManager, UserStore
from .capture.base import CaptureBackend, CaptureError
from .capture.media_browser import MediaBrowser, MediaFile, guess_media_type
from .capture.registry import build_capture_backend
from .config import DEFAULT_CONFIG_PATH, load_config, save_config
from .discovery import DiscoveredCamera, scan_network
from .models import AppConfig, CameraConfig, StorageConfig
from .motion import MotionWatcher
from .recording import RecordingSession
from .storage.base import StorageBackend, StorageError
from .storage.registry import build_storage_backend

app = FastAPI(title="CamControl Gateway")


class _GatewayState:
    def __init__(self) -> None:
        self.config_path = DEFAULT_CONFIG_PATH
        self.config: AppConfig = load_config(self.config_path)
        self._capture_backends: dict[str, CaptureBackend] = {}
        self._storage_backend: StorageBackend | None = None
        self._motion_watchers: dict[str, MotionWatcher] = {}
        self._recording_sessions: dict[str, RecordingSession] = {}
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

    def reload(self, config: AppConfig) -> None:
        self.stop_motion_watchers()
        for session in self._recording_sessions.values():
            session.stop()
        self._recording_sessions.clear()
        self.config = config
        self._capture_backends.clear()
        self._storage_backend = None
        save_config(config, self.config_path)
        self.start_motion_watchers()


state = _GatewayState()


@app.on_event("startup")
def _start_motion_watchers() -> None:
    state.start_motion_watchers()


@app.on_event("shutdown")
def _stop_motion_watchers() -> None:
    state.stop_motion_watchers()


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Legacy admin gate (env-configured shared secret). Used only for
    user-management endpoints, not for video/image access."""
    expected = os.environ.get("API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _require_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> str:
    """Video/image access gate: a valid bearer token from /api/auth/login,
    or (fallback) the legacy shared API_KEY for older/scripted clients."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[len("bearer ") :].strip()
        username = state.tokens.validate(token)
        if username is not None:
            return username
    expected = os.environ.get("API_KEY")
    if expected and x_api_key == expected:
        return "api_key"
    raise HTTPException(status_code=401, detail="Invalid or missing credentials")


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
def list_cameras(_: None = Depends(_require_api_key)) -> list[CameraSummary]:
    return [
        CameraSummary(id=c.id, name=c.name, type=c.type) for c in state.config.cameras
    ]


@app.get("/api/cameras/{camera_id}/motion", response_model=MotionStatus)
def get_motion_status(camera_id: str, _: None = Depends(_require_api_key)) -> MotionStatus:
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


@app.get("/api/discover", response_model=list[DiscoveredCamera])
async def discover_cameras(_: None = Depends(_require_api_key)) -> list[DiscoveredCamera]:
    """Scan the gateway host's own LAN subnet for candidate cameras."""
    return await scan_network()


@app.get("/api/cameras/{camera_id}/snapshot")
def get_snapshot(camera_id: str, _: str = Depends(_require_auth)) -> Response:
    backend = state.capture_backend_for(camera_id)
    try:
        jpeg = backend.get_snapshot()
    except CaptureError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=jpeg, media_type="image/jpeg")


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
def get_config(_: None = Depends(_require_api_key)) -> dict:
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
    cameras: list[CameraConfig], _: None = Depends(_require_api_key)
) -> dict:
    new_config = state.config.model_copy(update={"cameras": cameras})
    state.reload(new_config)
    return {"status": "ok", "cameras": len(cameras)}


@app.put("/api/config/storage")
def set_storage(storage: StorageConfig, _: None = Depends(_require_api_key)) -> dict:
    new_config = state.config.model_copy(update={"storage": storage})
    state.reload(new_config)
    return {"status": "ok", "provider": storage.provider}
