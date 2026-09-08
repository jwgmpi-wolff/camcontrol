import ipaddress

import pytest

from camera_bridge import discovery


@pytest.mark.asyncio
async def test_scan_network_aggregates_open_ports_and_fingerprint(monkeypatch):
    async def fake_probe_port(ip: str, port: int) -> bool:
        return ip == "10.0.0.5" and port in (22, 80)

    async def fake_fingerprint_http(ip: str):
        return "hi3518e_ssh", "third-party firmware about.html signature"

    monkeypatch.setattr(discovery, "_probe_port", fake_probe_port)
    monkeypatch.setattr(discovery, "_fingerprint_http", fake_fingerprint_http)

    network = ipaddress.ip_network("10.0.0.4/30", strict=False)
    results = await discovery.scan_network(network)

    assert len(results) == 1
    found = results[0]
    assert found.ip == "10.0.0.5"
    assert found.open_ports == [22, 80]
    assert found.suggested_type == "hi3518e_ssh"


@pytest.mark.asyncio
async def test_scan_network_returns_empty_when_nothing_open(monkeypatch):
    async def fake_probe_port(ip: str, port: int) -> bool:
        return False

    monkeypatch.setattr(discovery, "_probe_port", fake_probe_port)

    network = ipaddress.ip_network("10.0.0.4/30", strict=False)
    results = await discovery.scan_network(network)

    assert results == []
