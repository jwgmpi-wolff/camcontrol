"""Install and drive the on-camera CamControl configuration package.

The package lets a camera be reconfigured (ssh port, wifi, login account,
gateway API endpoint) from a phone over the camera's own Wi-Fi access point,
with the settings persisted in the camera's flash and applied on reboot.

Two delivery channels, matching the two ways these cameras can be reached:

* over SSH, straight into ``/home/yi-hack-v3/camcontrol`` (`install`), and
* via an SD card (`build_sd_card_bundle`), which is the recovery channel for
  a camera that is off the network entirely.

The upload path is ``cat > file`` over an exec channel, not SFTP -- this
firmware ships no sftp-server, the same constraint ``live_view_publisher``
and ``voice_message`` already work around.
"""

from __future__ import annotations

import shlex
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import paramiko
from pydantic import BaseModel, Field, field_validator

from .models import Hi3518eSshCameraConfig

CAMCONTROL_DIR = "/home/yi-hack-v3/camcontrol"
STAGE_DIR = "/tmp/camcontrol-install"

# A non-interactive SSH session on this firmware gets PATH=/usr/bin:/bin,
# which contains none of the camera's own binaries -- reboot, wpa_supplicant
# and friends all live under /home. Every command that needs them must widen
# PATH first or it fails with a silent "not found".
FIRMWARE_PATH = (
    "/home/base/tools:/home/yi-hack-v3/bin:/home/yi-hack-v3/sbin:"
    "/sbin:/usr/sbin:/bin:/usr/bin"
)
_PATH_EXPORT = f"export PATH=$PATH:{FIRMWARE_PATH}; "

# Uploaded to the staging dir; install.sh moves them into place.
_PAYLOAD_FILES = {
    "camcontrol-common.sh": "camcontrol-common.sh",
    "camcontrol-apply.sh": "camcontrol-apply.sh",
    "camcontrol-portal.sh": "camcontrol-portal.sh",
    "camcontrol-httpd.sh": "camcontrol-httpd.sh",
    "camcontrol-boot.sh": "camcontrol-boot.sh",
    "camcontrol.conf": "camcontrol.conf",
    "install.sh": "install.sh",
}

SECRET_KEYS = frozenset({"wifi_psk", "admin_password", "api_key", "ap_psk"})

# The portal is served over busybox nc because this firmware has no httpd and
# lwsws is static-file only; base64 backs the portal's basic auth.
_PROBE_TOOLS = (
    "dropbear",
    "wpa_supplicant",
    "wpa_cli",
    "nc",
    "base64",
    "ifconfig",
    "wget",
    "chpasswd",
)


class CameraProvisionError(RuntimeError):
    pass


class CameraProvisionSettings(BaseModel):
    """Settings pushed to a camera. Blank secrets mean "keep what's there"."""

    ssh_port: int | None = None
    wifi_ssid: str | None = None
    wifi_psk: str | None = None
    admin_user: str | None = None
    admin_password: str | None = None
    api_endpoint: str | None = None
    api_key: str | None = None
    camera_id: str | None = None
    push_interval_seconds: int | None = Field(default=None, ge=0)
    ap_ssid: str | None = None
    ap_psk: str | None = None
    ap_always: bool | None = None
    portal_port: int | None = None
    ap_timeout_seconds: int | None = Field(default=None, ge=0)
    wifi_wait_seconds: int | None = Field(default=None, ge=0)

    @field_validator("ssh_port", "portal_port")
    @classmethod
    def _valid_port(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return value

    @field_validator("ap_psk")
    @classmethod
    def _valid_ap_psk(cls, value: str | None) -> str | None:
        # An open AP would let anyone in range rewrite the camera's creds.
        if value and len(value) < 8:
            raise ValueError("ap_psk must be at least 8 characters")
        return value

    @field_validator("api_endpoint")
    @classmethod
    def _valid_endpoint(cls, value: str | None) -> str | None:
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("api_endpoint must start with http:// or https://")
        return value

    def to_config_entries(self) -> dict[str, str]:
        entries: dict[str, str] = {}
        for key, value in self.model_dump(exclude_none=True).items():
            if isinstance(value, bool):
                entries[key] = "1" if value else "0"
            else:
                entries[key] = str(value)
        return entries


@dataclass(frozen=True)
class CameraCapabilities:
    """What the firmware can actually do, probed before promising anything."""

    tools: dict[str, bool]
    wifi_interface: str
    persistent_dir_writable: bool
    boot_hook_candidates: tuple[str, ...]
    package_installed: bool

    @property
    def can_serve_portal(self) -> bool:
        return self.tools.get("nc", False) and self.tools.get("base64", False)

    @property
    def can_host_ap(self) -> bool:
        return self.tools.get("wpa_supplicant", False)

    @property
    def blocking_issues(self) -> list[str]:
        issues: list[str] = []
        if not self.persistent_dir_writable:
            issues.append(
                f"{CAMCONTROL_DIR} is not writable; the package cannot persist"
            )
        if not self.can_host_ap:
            issues.append(
                "wpa_supplicant is missing; the camera cannot raise a setup "
                "access point"
            )
        if not self.can_serve_portal:
            issues.append(
                "busybox nc/base64 are missing; the web portal cannot be "
                "served (SSH and SD-card configuration still work)"
            )
        if not self.boot_hook_candidates:
            issues.append(
                "no writable startup script found; the boot hook must be "
                "installed manually"
            )
        return issues


def load_payload() -> dict[str, bytes]:
    """Reads the on-camera package out of the installed Python package."""
    payload: dict[str, bytes] = {}
    root = resources.files(__package__).joinpath("oncam")
    for remote_name, relative in _PAYLOAD_FILES.items():
        resource = root
        for part in relative.split("/"):
            resource = resource.joinpath(part)
        # LF only: busybox ash chokes on CRLF shebang lines.
        text = resource.read_text(encoding="utf-8").replace("\r\n", "\n")
        payload[remote_name] = text.encode("utf-8")
    return payload


def parse_config_text(text: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        entries[key.strip()] = value.strip()
    return entries


def merge_config(
    current: dict[str, str], updates: dict[str, str]
) -> dict[str, str]:
    """Applies updates, treating a blank secret as "keep the stored value"."""
    merged = dict(current)
    for key, value in updates.items():
        if key in SECRET_KEYS and value == "":
            continue
        merged[key] = value
    return merged


def render_config_text(entries: dict[str, str]) -> str:
    lines = [
        "# CamControl on-camera configuration.",
        "# Generated by the gateway; applied on the next camera reboot.",
    ]
    lines.extend(f"{key}={value}" for key, value in sorted(entries.items()))
    return "\n".join(lines) + "\n"


def redact_config(entries: dict[str, str]) -> dict[str, str]:
    """Never hand raw camera secrets back to an API caller or a log."""
    return {
        key: ("***" if value else "")
        if key in SECRET_KEYS
        else value
        for key, value in entries.items()
    }


def build_sd_card_bundle(
    destination: Path, settings: CameraProvisionSettings | None = None
) -> list[Path]:
    """Writes the SD-card recovery bundle.

    ``camcontrol.conf`` at the card root is imported on the next boot by an
    already-installed package. ``camcontrol-install/`` carries the full
    package so a camera can be installed by hand from a shell when no boot
    hook exists yet.
    """
    destination.mkdir(parents=True, exist_ok=True)
    stage = destination / "camcontrol-install"
    stage.mkdir(exist_ok=True)

    written: list[Path] = []
    for remote_name, data in load_payload().items():
        target = stage / remote_name
        target.write_bytes(data)
        written.append(target)

    if settings is not None:
        entries = settings.to_config_entries()
        if entries:
            card_conf = destination / "camcontrol.conf"
            card_conf.write_text(render_config_text(entries), encoding="utf-8")
            written.append(card_conf)

    readme = destination / "CAMCONTROL-README.txt"
    readme.write_text(
        "CamControl SD card bundle\n"
        "=========================\n\n"
        "Reconfigure an already-provisioned camera:\n"
        "  1. Copy camcontrol.conf to the root of a FAT32 card.\n"
        "  2. Power the camera off, insert the card, power it on.\n"
        "  3. The settings are imported and applied during boot, then the\n"
        "     file is renamed to camcontrol.conf.applied so a card left in\n"
        "     the slot stops overriding later changes.\n\n"
        "First-time install with no boot hook yet (needs shell access):\n"
        "  STAGE_DIR=/tmp/sd/camcontrol-install "
        "sh /tmp/sd/camcontrol-install/install.sh\n\n"
        "This file contains no credentials. camcontrol.conf does -- erase\n"
        "the card once the camera has booted.\n",
        encoding="utf-8",
    )
    written.append(readme)
    return written


class CameraProvisioner:
    """Installs and drives the on-camera package over SSH."""

    def __init__(self, config: Hi3518eSshCameraConfig) -> None:
        self._config = config

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self._config.host,
            port=self._config.port,
            username=self._config.username,
            password=self._config.password,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        return client

    def _run(
        self, client: paramiko.SSHClient, command: str, timeout: int = 20
    ) -> tuple[str, str, int]:
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        stdout.channel.settimeout(timeout)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        return out, err, stdout.channel.recv_exit_status()

    def _upload(
        self,
        client: paramiko.SSHClient,
        data: bytes,
        remote_path: str,
        timeout: int = 20,
    ) -> None:
        stdin, stdout, stderr = client.exec_command(
            f"cat > {shlex.quote(remote_path)}", timeout=timeout
        )
        stdout.channel.settimeout(timeout)
        stdin.write(data)
        stdin.channel.shutdown_write()
        stdout.read()
        error = stderr.read().decode(errors="replace").strip()
        if stdout.channel.recv_exit_status() != 0 or error:
            raise CameraProvisionError(
                f"Upload of {remote_path} failed: {error or 'unknown error'}"
            )

    def probe(self) -> CameraCapabilities:
        client = self._connect()
        try:
            # A tool counts as present if it is on the firmware's own PATH or
            # available as a busybox applet; a bare `command -v` under the
            # minimal non-interactive SSH PATH reports false negatives.
            checks = "; ".join(
                f'if command -v {tool} >/dev/null 2>&1 || '
                f'busybox --list 2>/dev/null | grep -qx {tool}; '
                f'then echo "tool {tool} 1"; else echo "tool {tool} 0"; fi'
                for tool in _PROBE_TOOLS
            )
            command = (
                _PATH_EXPORT
                + f"{checks}; "
                "for i in wlan0 wlan1 ra0 apcli0; do "
                '[ -e /sys/class/net/$i ] && echo "iface $i" && break; done; '
                f"mkdir -p {CAMCONTROL_DIR} 2>/dev/null "
                f'&& [ -w {CAMCONTROL_DIR} ] && echo "persist 1" '
                '|| echo "persist 0"; '
                f'[ -f {CAMCONTROL_DIR}/bin/camcontrol-boot.sh ] '
                '&& echo "installed 1" || echo "installed 0"; '
                "for f in /home/yi-hack-v3/startup.sh "
                "/home/yi-hack-v3/script/run.sh "
                "/home/yi-hack-v3/etc/init.d/rcS /home/init.sh "
                "/etc/init.d/rcS; do "
                '[ -f "$f" ] && [ -w "$f" ] && echo "hook $f"; done'
            )
            out, _err, _code = self._run(client, command, timeout=25)
        finally:
            client.close()

        tools = {tool: False for tool in _PROBE_TOOLS}
        interface = "wlan0"
        persistent = False
        installed = False
        hooks: list[str] = []
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            kind, value = parts[0], parts[1]
            if kind == "tool" and len(parts) >= 3:
                tools[value] = parts[2] == "1"
            elif kind == "iface":
                interface = value
            elif kind == "persist":
                persistent = value == "1"
            elif kind == "installed":
                installed = value == "1"
            elif kind == "hook":
                hooks.append(value)

        return CameraCapabilities(
            tools=tools,
            wifi_interface=interface,
            persistent_dir_writable=persistent,
            boot_hook_candidates=tuple(hooks),
            package_installed=installed,
        )

    def install(self) -> str:
        """Uploads the package and runs the on-device installer."""
        payload = load_payload()
        client = self._connect()
        try:
            _out, err, code = self._run(
                client, f"mkdir -p {shlex.quote(STAGE_DIR)}"
            )
            if code != 0:
                raise CameraProvisionError(
                    f"Cannot create staging directory: {err.strip() or code}"
                )
            for name, data in payload.items():
                self._upload(client, data, f"{STAGE_DIR}/{name}")

            out, err, code = self._run(
                client,
                f"STAGE_DIR={shlex.quote(STAGE_DIR)} "
                f"sh {shlex.quote(STAGE_DIR)}/install.sh 2>&1",
                timeout=60,
            )
            if code != 0:
                raise CameraProvisionError(
                    f"Installer failed: {(out + err).strip() or code}"
                )
            self._run(client, f"rm -rf {shlex.quote(STAGE_DIR)}", timeout=15)
            return out
        finally:
            client.close()

    def read_config(self) -> dict[str, str]:
        client = self._connect()
        try:
            out, _err, code = self._run(
                client, f"cat {shlex.quote(CAMCONTROL_DIR)}/camcontrol.conf"
            )
            if code != 0:
                raise CameraProvisionError(
                    "Configuration package is not installed on this camera"
                )
            return parse_config_text(out)
        finally:
            client.close()

    def write_config(self, settings: CameraProvisionSettings) -> dict[str, str]:
        updates = settings.to_config_entries()
        client = self._connect()
        try:
            out, _err, code = self._run(
                client, f"cat {shlex.quote(CAMCONTROL_DIR)}/camcontrol.conf"
            )
            if code != 0:
                raise CameraProvisionError(
                    "Configuration package is not installed on this camera"
                )
            merged = merge_config(parse_config_text(out), updates)
            remote = f"{CAMCONTROL_DIR}/camcontrol.conf"
            self._upload(client, render_config_text(merged).encode(), remote)
            self._run(client, f"chmod 600 {shlex.quote(remote)}", timeout=10)
            return merged
        finally:
            client.close()

    def reboot(self) -> None:
        client = self._connect()
        try:
            # Not backgrounded and not waited on: a detached `(sleep; reboot)&`
            # is SIGHUPed when this SSH session closes, which silently
            # cancelled the reboot. Firing it directly means the connection
            # simply drops, so no exit status is read.
            client.exec_command(_PATH_EXPORT + "reboot", timeout=10)
            time.sleep(1)
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
