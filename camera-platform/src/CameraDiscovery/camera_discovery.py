"""
Camera discovery engine for YI YHS.3017 and compatible devices.
Performs ARP-sweep, safe port probing, RTSP/ONVIF/HTTP detection,
and produces a JSON capability report.

Does NOT:
- brute-force credentials
- exploit firmware
- attempt default-credential login
- use hidden developer modes
"""

from __future__ import annotations

import json
import logging
import platform
import socket
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from ipaddress import IPv4Network, ip_address
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

# Safe ports only – no management plane or exploit surface
SAFE_PORTS = [80, 443, 554, 8000, 8080, 8899, 1900]

# RTSP paths documented in community databases and vendor SDK examples.
# We only TRY these URLs after the user supplies their own credentials.
RTSP_PATH_CANDIDATES = [
    "/ch0_0.h264",
    "/ch0_1.h264",
    "/live",
    "/stream1",
    "/ch0_0.h264",  # yi-hack-Allwinner-v2 YI Outdoor 1080p (h30ga/r40ga)
]


@dataclass(slots=True)
class PortResult:
    port: int
    open: bool
    service_hint: str


@dataclass(slots=True)
class CameraCandidate:
    ip_address: str
    hostname: str | None
    mac_address: str | None
    open_ports: list[int]
    rtsp_likely: bool
    http_likely: bool
    https_likely: bool
    onvif_candidate: bool
    rtsp_path_candidates: list[str]
    safe_next_steps: list[str]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def probe_port(ip: str, port: int, timeout_s: float = 0.7) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout_s):
            return True
    except (OSError, TimeoutError):
        return False


def resolve_hostname(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror):
        return None


def get_arp_table() -> dict[str, str]:
    """Return {ip: mac} from the OS ARP table (cross-platform)."""
    mapping: dict[str, str] = {}
    try:
        if platform.system() == "Windows":
            out = subprocess.check_output(["arp", "-a"], text=True, timeout=10)
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0].count(".") == 3:
                    try:
                        ip_address(parts[0])
                        mapping[parts[0]] = parts[1]
                    except ValueError:
                        pass
        else:
            # Linux: /proc/net/arp or `arp -n`
            arp_path = Path("/proc/net/arp")
            if arp_path.exists():
                for line in arp_path.read_text().splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 4:
                        mapping[parts[0]] = parts[3]
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("ARP table read failed: %s", exc)
    return mapping


def ping_sweep(subnet_prefix: str, timeout_s: float = 0.3) -> None:
    """Warm the ARP table with a non-blocking ICMP sweep."""
    flag = "-n" if platform.system() == "Windows" else "-c"
    for i in range(1, 255):
        ip = f"{subnet_prefix}.{i}"
        try:
            subprocess.Popen(
                ["ping", flag, "1", "-W", "1", ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:  # noqa: BLE001
            pass


def local_subnet_prefix() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        addr = s.getsockname()[0]
    finally:
        s.close()
    parts = addr.split(".")
    return f"{parts[0]}.{parts[1]}.{parts[2]}"


def build_rtsp_candidates(ip: str) -> list[str]:
    return [f"rtsp://{ip}:554{path}" for path in RTSP_PATH_CANDIDATES]


def assess_candidate(ip: str, mac: str | None, ports: list[int]) -> CameraCandidate:
    hostname = resolve_hostname(ip)
    rtsp_likely = 554 in ports
    http_likely = 80 in ports or 8080 in ports
    https_likely = 443 in ports
    onvif_candidate = any(p in ports for p in [8000, 8899, 80])

    next_steps = [
        "Confirm this IP belongs to your YI YHS.3017 in your router DHCP table or YI app.",
    ]
    if rtsp_likely:
        next_steps += [
            "Port 554 is open. Test RTSP with your own configured credentials using VLC or FFmpeg.",
            "Try candidate URL: rtsp://<your-user>:<your-pass>@{ip}:554/ch0_0.264".format(ip=ip),
            "Do NOT attempt brute-force or default credentials.",
        ]
    if http_likely:
        next_steps.append("An HTTP endpoint is open. Check your router for the device page URL.")
    if onvif_candidate:
        next_steps.append("ONVIF port may be open. Test with an ONVIF client using your credentials.")

    return CameraCandidate(
        ip_address=ip,
        hostname=hostname,
        mac_address=mac,
        open_ports=ports,
        rtsp_likely=rtsp_likely,
        http_likely=http_likely,
        https_likely=https_likely,
        onvif_candidate=onvif_candidate,
        rtsp_path_candidates=build_rtsp_candidates(ip) if rtsp_likely else [],
        safe_next_steps=next_steps,
    )


def discover(
    subnet_prefix: str | None = None,
    ports: list[int] | None = None,
    timeout_s: float = 0.7,
    max_workers: int = 64,
    output_path: str | None = None,
) -> list[CameraCandidate]:
    if subnet_prefix is None:
        subnet_prefix = local_subnet_prefix()
    if ports is None:
        ports = SAFE_PORTS

    LOGGER.info("Warming ARP table with ping sweep on %s.0/24", subnet_prefix)
    ping_sweep(subnet_prefix)

    arp = get_arp_table()

    def probe_ip(ip: str) -> tuple[str, list[int]]:
        open_ports = [p for p in ports if probe_port(ip, p, timeout_s)]
        return ip, open_ports

    LOGGER.info("Probing ports %s on %s.0/24", ports, subnet_prefix)
    candidates: list[CameraCandidate] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(probe_ip, f"{subnet_prefix}.{i}"): f"{subnet_prefix}.{i}"
            for i in range(1, 255)
        }
        for future in as_completed(futures):
            ip, open_ports = future.result()
            if open_ports:
                mac = arp.get(ip)
                candidates.append(assess_candidate(ip, mac, open_ports))

    report = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "target_model": "YI Outdoor Camera 1080p YHS.3017",
        "subnet_scanned": f"{subnet_prefix}.0/24",
        "ports_checked": ports,
        "devices_found": len(candidates),
        "devices": [c.to_dict() for c in candidates],
    }

    if output_path:
        Path(output_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
        LOGGER.info("Report written to %s", output_path)

    return candidates


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    results = discover(output_path="camera-discovery-report.json")
    for c in results:
        status = []
        if c.rtsp_likely:
            status.append("RTSP")
        if c.http_likely:
            status.append("HTTP")
        if c.onvif_candidate:
            status.append("ONVIF?")
        print(f"{c.ip_address:16s}  {c.mac_address or '?':17s}  ports={c.open_ports}  [{', '.join(status)}]")
