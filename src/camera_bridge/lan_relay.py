"""Low-memory LAN relay for cameras that cannot make HTTPS requests."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import threading
from urllib.parse import urlparse

import httpx
import paramiko
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request

MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
DEFAULT_TARGET = "https://camcontrol-wolff.azurewebsites.net"

app = FastAPI(title="CamControl LAN Relay")
logger = logging.getLogger(__name__)
_ssh_clients: dict[str, paramiko.SSHClient] = {}
_ssh_clients_lock = threading.Lock()


def camera_key_is_valid(camera_id: str, camera_key: str | None, master_key: str) -> bool:
    expected = hmac.new(
        master_key.encode(), camera_id.encode(), hashlib.sha256
    ).hexdigest()
    return bool(master_key and camera_key) and hmac.compare_digest(camera_key, expected)


def camera_key_for(camera_id: str, master_key: str) -> str:
    return hmac.new(master_key.encode(), camera_id.encode(), hashlib.sha256).hexdigest()


async def forward_snapshot(camera_id: str, payload: bytes, camera_key: str) -> None:
    target = os.environ.get("CAMCONTROL_RELAY_TARGET", DEFAULT_TARGET).rstrip("/")
    target_url = f"{target}/api/cameras/{camera_id}/push-snapshot"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            target_url,
            content=payload,
            headers={
                "Content-Type": "image/jpeg" if payload.startswith(b"\xff\xd8") else "video/h264",
                "X-Camera-Key": camera_key,
            },
        )
    response.raise_for_status()


def configured_cameras() -> list[tuple[str, str]]:
    configured = os.environ.get("CAMCONTROL_RELAY_CAMERAS", "")
    if configured:
        cameras: list[tuple[str, str]] = []
        for entry in configured.split(","):
            camera_id, separator, camera_url = entry.partition("=")
            if separator and camera_id and camera_url:
                cameras.append((camera_id.strip(), camera_url.strip()))
        return cameras
    camera_url = os.environ.get("CAMCONTROL_RELAY_CAMERA_URL", "")
    camera_id = os.environ.get("CAMCONTROL_RELAY_CAMERA_ID", "")
    return [(camera_id, camera_url)] if camera_id and camera_url else []


def _connect_ssh_preview(camera_url: str) -> paramiko.SSHClient:
    parsed = urlparse(camera_url)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=parsed.hostname,
        port=parsed.port or 22,
        username=parsed.username or os.environ.get("CAMCONTROL_RELAY_SSH_USER", "root"),
        password=os.environ.get("CAMCONTROL_RELAY_SSH_PASSWORD", ""),
        timeout=15,
        banner_timeout=15,
        auth_timeout=15,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def _read_ssh_preview(camera_url: str) -> bytes:
    with _ssh_clients_lock:
        client = _ssh_clients.get(camera_url)
        if client is None or not client.get_transport() or not client.get_transport().is_active():
            if client is not None:
                client.close()
            client = _connect_ssh_preview(camera_url)
            _ssh_clients[camera_url] = client
    try:
        _stdin, stdout, _stderr = client.exec_command("cat /tmp/view", timeout=20)
        stdout.channel.settimeout(20)
        return stdout.read()
    except Exception:
        with _ssh_clients_lock:
            if _ssh_clients.get(camera_url) is client:
                _ssh_clients.pop(camera_url, None)
        client.close()
        raise


async def poll_camera(camera_id: str, camera_url: str) -> None:
    master_key = os.environ.get("CAMCONTROL_API_KEY", "")
    if not master_key:
        return
    interval = max(1, int(os.environ.get("CAMCONTROL_RELAY_INTERVAL", "5")))
    camera_key = camera_key_for(camera_id, master_key)
    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            try:
                if camera_url.startswith("ssh://"):
                    payload = await asyncio.to_thread(_read_ssh_preview, camera_url)
                else:
                    response = await client.get(camera_url)
                    response.raise_for_status()
                    payload = response.content
                await forward_snapshot(camera_id, payload, camera_key)
            except httpx.HTTPError:
                logger.warning("Camera relay poll failed", exc_info=True)
            await asyncio.sleep(interval)


@app.on_event("startup")
async def start_camera_poller() -> None:
    for camera_id, camera_url in configured_cameras():
        asyncio.create_task(poll_camera(camera_id, camera_url))


@app.post("/api/cameras/{camera_id}/push-snapshot")
async def push_snapshot(
    camera_id: str,
    request: Request,
    x_camera_key: str | None = Header(default=None),
) -> dict[str, str]:
    master_key = os.environ.get("CAMCONTROL_API_KEY", "")
    if not camera_key_is_valid(camera_id, x_camera_key, master_key):
        raise HTTPException(status_code=401, detail="Invalid camera credentials")

    payload = await request.body()
    if not payload or len(payload) > MAX_SNAPSHOT_BYTES:
        raise HTTPException(status_code=400, detail="Invalid snapshot payload")

    try:
        await forward_snapshot(camera_id, payload, x_camera_key)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Gateway unavailable") from exc
    return {"status": "ok"}


def main() -> None:
    host = os.environ.get("CAMCONTROL_RELAY_HOST", "0.0.0.0")
    port = int(os.environ.get("CAMCONTROL_RELAY_PORT", "21417"))
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()