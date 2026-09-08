"""Local-network camera discovery: scan the gateway host's own subnet for
candidate cameras (open SSH/HTTP/RTSP ports), then fingerprint port 80 to
suggest which capture backend type likely applies.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket

import httpx
from pydantic import BaseModel

_CANDIDATE_PORTS = (22, 80, 554)
_CONNECT_TIMEOUT = 0.35
_HTTP_TIMEOUT = 1.5
_CONCURRENCY = 128


class DiscoveredCamera(BaseModel):
    ip: str
    open_ports: list[int]
    suggested_type: str  # "hi3518e_ssh" | "rtsp" | "unknown"
    suggested_name: str
    fingerprint: str


def get_local_subnet() -> ipaddress.IPv4Network:
    """Best-effort /24 around this host's own LAN-facing IP address."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    return ipaddress.ip_network(f"{local_ip}/24", strict=False)


async def _probe_port(ip: str, port: int) -> bool:
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=_CONNECT_TIMEOUT
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return True
    except Exception:  # noqa: BLE001
        return False


async def _fingerprint_http(ip: str) -> tuple[str, str]:
    """Returns (suggested_type, fingerprint) based on what's on port 80."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            res = await client.get(f"http://{ip}/about.html")
            if res.status_code == 200 and "custom firmware" in res.text.lower():
                return "hi3518e_ssh", "third-party firmware about.html signature"
        except Exception:  # noqa: BLE001
            pass
        try:
            res = await client.get(f"http://{ip}/")
            if res.status_code == 200:
                text = res.text.lower()
                if "custom firmware" in text or "software version informations" in text:
                    return "unknown", "third-party-firmware-family HTTP page (unconfirmed variant)"
                return "unknown", "HTTP server present, unrecognized"
        except Exception:  # noqa: BLE001
            pass
    return "unknown", "no HTTP response"


async def _probe_host(ip: str, semaphore: asyncio.Semaphore) -> DiscoveredCamera | None:
    async with semaphore:
        open_ports = []
        for port in _CANDIDATE_PORTS:
            if await _probe_port(ip, port):
                open_ports.append(port)
        if not open_ports:
            return None

        suggested_type = "unknown"
        fingerprint = f"open ports: {open_ports}"
        if 80 in open_ports:
            suggested_type, fingerprint = await _fingerprint_http(ip)
        if suggested_type == "unknown" and 554 in open_ports:
            suggested_type = "rtsp"
            fingerprint = "RTSP port open, no third-party firmware HTTP signature"

        return DiscoveredCamera(
            ip=ip,
            open_ports=open_ports,
            suggested_type=suggested_type,
            suggested_name=f"Camera {ip}",
            fingerprint=fingerprint,
        )


async def scan_network(network: ipaddress.IPv4Network | None = None) -> list[DiscoveredCamera]:
    network = network or get_local_subnet()
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    hosts = [str(h) for h in network.hosts()]
    results = await asyncio.gather(*(_probe_host(ip, semaphore) for ip in hosts))
    return [r for r in results if r is not None]
