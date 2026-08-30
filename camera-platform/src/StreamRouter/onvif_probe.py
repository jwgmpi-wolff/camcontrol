"""
ONVIF WS-Discovery probe.
Uses only the multicast discovery protocol (UDP 3702) – no authentication bypass.
Reports whether the device responds; user must supply credentials separately.
"""

from __future__ import annotations

import logging
import socket
import uuid
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)

WS_DISCOVERY_ADDRESS = "239.255.255.250"
WS_DISCOVERY_PORT = 3702

WS_DISCOVERY_MSG = """\
<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope
  xmlns:e="http://www.w3.org/2003/05/soap-envelope"
  xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
  xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <e:Header>
    <w:MessageID>uuid:{msg_id}</w:MessageID>
    <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
  </e:Header>
  <e:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </e:Body>
</e:Envelope>"""


@dataclass(slots=True)
class OnvifDevice:
    ip_address: str
    endpoint_ref: str
    types: str
    scopes: str
    service_url: str


def discover_onvif(timeout_s: float = 3.0) -> list[OnvifDevice]:
    """Send WS-Discovery probe and collect responses."""
    msg = WS_DISCOVERY_MSG.format(msg_id=str(uuid.uuid4())).encode("utf-8")
    devices: list[OnvifDevice] = []

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout_s)
        sock.sendto(msg, (WS_DISCOVERY_ADDRESS, WS_DISCOVERY_PORT))

        while True:
            try:
                data, addr = sock.recvfrom(4096)
                text = data.decode("utf-8", errors="replace")
                device = _parse_probe_match(text, addr[0])
                if device:
                    devices.append(device)
            except TimeoutError:
                break
        sock.close()
    except OSError as exc:
        LOGGER.warning("ONVIF WS-Discovery failed: %s", exc)

    return devices


def _extract_tag(xml: str, tag: str) -> str:
    import re
    match = re.search(rf"<[^>]*{tag}[^>]*>(.*?)<", xml, re.DOTALL)
    return match.group(1).strip() if match else ""


def _parse_probe_match(xml: str, source_ip: str) -> OnvifDevice | None:
    if "ProbeMatch" not in xml:
        return None
    endpoint = _extract_tag(xml, "EndpointReference")
    types = _extract_tag(xml, "Types")
    scopes = _extract_tag(xml, "Scopes")
    xaddrs = _extract_tag(xml, "XAddrs")
    service_url = xaddrs.split()[0] if xaddrs.split() else f"http://{source_ip}/onvif/device_service"
    return OnvifDevice(
        ip_address=source_ip,
        endpoint_ref=endpoint,
        types=types,
        scopes=scopes,
        service_url=service_url,
    )
