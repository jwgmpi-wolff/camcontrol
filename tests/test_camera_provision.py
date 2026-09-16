"""Tests for the on-camera configuration package and its installer.

The shell payload is exercised structurally (it runs on busybox ash on the
camera, not here), and the SSH install/probe paths run against a fake
paramiko client so no test ever touches a real camera.
"""

from __future__ import annotations

import pytest

from camera_bridge.camera_provision import (
    CAMCONTROL_DIR,
    SECRET_KEYS,
    CameraProvisioner,
    CameraProvisionSettings,
    build_sd_card_bundle,
    load_payload,
    merge_config,
    parse_config_text,
    redact_config,
    render_config_text,
)
from camera_bridge.models import Hi3518eSshCameraConfig

_SHELL_PAYLOAD = (
    "camcontrol-common.sh",
    "camcontrol-apply.sh",
    "camcontrol-portal.sh",
    "camcontrol-httpd.sh",
    "camcontrol-boot.sh",
    "install.sh",
)


class _FakeChannel:
    def __init__(self, exit_status: int = 0) -> None:
        self._exit_status = exit_status

    def settimeout(self, _timeout) -> None:
        return None

    def shutdown_write(self) -> None:
        return None

    def recv_exit_status(self) -> int:
        return self._exit_status


class _FakeStream:
    def __init__(self, data: bytes = b"", exit_status: int = 0) -> None:
        self._data = data
        self.channel = _FakeChannel(exit_status)
        self.written = b""

    def read(self) -> bytes:
        return self._data

    def write(self, data: bytes) -> None:
        self.written += data


class _FakeSSHClient:
    """Records commands and serves canned stdout per matching substring."""

    def __init__(self, responses: dict[str, bytes] | None = None) -> None:
        self.responses = responses or {}
        self.commands: list[str] = []
        self.uploads: dict[str, bytes] = {}
        self.closed = False

    def exec_command(self, command: str, timeout: int = 0):
        self.commands.append(command)
        stdin = _FakeStream()
        payload = b""
        for needle, data in self.responses.items():
            if needle in command:
                payload = data
                break
        stdout = _FakeStream(payload)
        stderr = _FakeStream()
        if command.startswith("cat > "):
            path = command[len("cat > ") :].strip().strip("'\"")
            self._pending_upload = (path, stdin)
            stdout = _UploadAwareStream(self, path, stdin)
        return stdin, stdout, stderr

    def close(self) -> None:
        self.closed = True


class _UploadAwareStream(_FakeStream):
    def __init__(self, client: _FakeSSHClient, path: str, stdin: _FakeStream) -> None:
        super().__init__(b"")
        self._client = client
        self._path = path
        self._stdin = stdin

    def read(self) -> bytes:
        self._client.uploads[self._path] = self._stdin.written
        return b""


def _camera() -> Hi3518eSshCameraConfig:
    return Hi3518eSshCameraConfig(id="cam-1", name="Cam 1", host="10.0.0.1")


def _provisioner(client: _FakeSSHClient) -> CameraProvisioner:
    provisioner = CameraProvisioner(_camera())
    provisioner._connect = lambda: client  # type: ignore[method-assign]
    return provisioner


def test_payload_ships_every_on_camera_file():
    payload = load_payload()

    assert set(payload) == {
        "camcontrol-common.sh",
        "camcontrol-apply.sh",
        "camcontrol-portal.sh",
        "camcontrol-httpd.sh",
        "camcontrol-boot.sh",
        "camcontrol.conf",
        "install.sh",
    }


@pytest.mark.parametrize("name", _SHELL_PAYLOAD)
def test_shell_payload_is_busybox_safe(name):
    body = load_payload()[name].decode()
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )

    # A CRLF shebang makes busybox ash fail with a confusing "not found".
    assert "\r" not in body, f"{name} must use LF line endings"
    assert body.startswith("#!/bin/sh"), f"{name} must target /bin/sh"
    assert "[[" not in code, f"{name} must avoid the bash [[ builtin"
    assert "function " not in code, f"{name} must use POSIX function syntax"


def test_boot_script_raises_ap_only_after_wifi_fails():
    body = load_payload()["camcontrol-boot.sh"].decode()

    # Ordering is the safety property: a bad wifi password must self-recover
    # into the setup AP rather than locking the camera out.
    assert body.index("cc_import_sd_config") < body.index("camcontrol-apply.sh")
    assert body.index("cc_wifi_associated") < body.index(
        "boot: wifi did not associate"
    )
    assert "camcontrol.conf.applied" not in body or ".applied" in body


def test_portal_refuses_to_serve_without_a_password():
    body = load_payload()["camcontrol-portal.sh"].decode()

    assert "refusing to start without a login password" in body
    # An open AP would let anyone in range rewrite the camera's credentials.
    assert "ap_psk must be at least 8 characters" in body


def test_ap_arms_reboot_watchdog_before_touching_wifi():
    body = load_payload()["camcontrol-portal.sh"].decode()

    # Raising the AP drops the client wifi link, which on a headless camera
    # is the one step that could strand it; the watchdog must be armed first.
    assert "camcontrol-watchdog-disarm" in body
    dispatch = body.split('case "${1:-start}"', 1)[1]
    assert dispatch.index("cc_arm_watchdog") < dispatch.index("cc_ap_start")
    # The live AP test must also be self-recovering.
    test_case = dispatch.split("test)", 1)[1]
    assert test_case.index("cc_arm_watchdog") < test_case.index("cc_ap_start")


def test_boot_leaves_firmware_wifi_alone_when_camcontrol_does_not_manage_it():
    body = load_payload()["camcontrol-boot.sh"].decode()

    # With no wifi_ssid of its own, camcontrol is a passenger on the
    # firmware's wifi config. Raising the setup AP there knocks a healthy
    # camera off the network instead of recovering a broken one.
    guard = body.index('cc_get wifi_ssid ""')
    assert guard < body.index("boot: wifi did not associate")
    assert "leaving firmware wifi alone" in body
    # The association wait must be tunable, since it expiring early is what
    # triggered the takeover in the first place.
    assert "wifi_wait_seconds" in body


def test_ap_is_not_raised_when_the_portal_could_not_serve():
    body = load_payload()["camcontrol-portal.sh"].decode()
    dispatch = body.split('case "${1:-start}"', 1)[1]

    # Readiness is checked before the watchdog and before any wifi change:
    # an AP with no reachable portal is worse than staying on the network.
    assert dispatch.index("cc_portal_ready") < dispatch.index("cc_arm_watchdog")
    assert dispatch.index("cc_portal_ready") < dispatch.index("cc_ap_start")
    test_case = dispatch.split("test)", 1)[1]
    assert test_case.index("cc_portal_ready") < test_case.index("cc_ap_start")


def test_failed_portal_tears_the_ap_back_down():
    body = load_payload()["camcontrol-portal.sh"].decode()

    # If the portal dies after the AP is up, recover immediately rather than
    # stranding the camera until the watchdog eventually fires.
    assert "cc_portal_start || cc_ap_abort" in body
    assert "cc_ap_abort()" in body


def test_portal_uses_nc_because_the_firmware_has_no_httpd():
    body = load_payload()["camcontrol-httpd.sh"].decode()

    assert "nc -l -p" in body
    assert "401 Unauthorized" in body
    assert "WWW-Authenticate: Basic" in body


def test_portal_form_never_renders_stored_secrets():
    body = load_payload()["camcontrol-httpd.sh"].decode()

    for secret in ("wifi_psk", "admin_password", "api_key", "ap_psk"):
        assert f'value="$(cc_html "$(cc_get {secret}' not in body


def test_common_script_widens_path_before_probing_for_tools():
    body = load_payload()["camcontrol-common.sh"].decode()

    # A non-interactive SSH session has none of the firmware's own binary
    # directories on PATH, which made every tool look missing.
    assert "/home/base/tools" in body
    assert "/home/yi-hack-v3/bin" in body
    assert "export PATH" in body
    # Several of these tools exist only as busybox applets.
    assert "busybox --list" in body
    assert "cc_tool()" in body


def test_probe_command_detects_busybox_applets_on_the_firmware_path():
    captured: dict[str, str] = {}

    class _RecordingClient(_FakeSSHClient):
        def exec_command(self, command: str, timeout: int = 0):
            captured["command"] = command
            return super().exec_command(command, timeout)

    _provisioner(_RecordingClient()).probe()

    assert "/home/base/tools" in captured["command"]
    assert "busybox --list" in captured["command"]


@pytest.mark.parametrize("name", _SHELL_PAYLOAD)
def test_shell_payload_avoids_applets_this_firmware_lacks(name):
    """The camera's busybox build has no head/wc/expr/sort/uniq.

    `cc_get` is built on this, so a stray `head` silently breaks every
    setting read rather than failing loudly.
    """
    code = "\n".join(
        line
        for line in load_payload()[name].decode().splitlines()
        if not line.lstrip().startswith("#")
    )

    for applet in ("head", "wc", "expr", "sort", "uniq"):
        assert f"| {applet} " not in code, f"{name} pipes into missing {applet}"
        assert f"$({applet} " not in code, f"{name} calls missing {applet}"
        assert not code.startswith(f"{applet} ")


def test_parse_and_render_config_round_trip():
    text = "# comment\nssh_port=2222\nwifi_ssid=Home Net\n\nap_always=1\n"

    entries = parse_config_text(text)

    assert entries == {
        "ssh_port": "2222",
        "wifi_ssid": "Home Net",
        "ap_always": "1",
    }
    assert parse_config_text(render_config_text(entries)) == entries


def test_merge_keeps_stored_secret_when_update_is_blank():
    current = {"wifi_psk": "stored", "ssh_port": "22"}

    merged = merge_config(current, {"wifi_psk": "", "ssh_port": "2222"})

    assert merged["wifi_psk"] == "stored"
    assert merged["ssh_port"] == "2222"


def test_merge_replaces_secret_when_a_new_value_is_given():
    merged = merge_config({"api_key": "old"}, {"api_key": "new"})

    assert merged["api_key"] == "new"


def test_redact_config_hides_every_secret_field():
    entries = {key: "sensitive" for key in SECRET_KEYS}
    entries["ssh_port"] = "22"

    redacted = redact_config(entries)

    assert redacted["ssh_port"] == "22"
    for key in SECRET_KEYS:
        assert redacted[key] == "***"


def test_redact_config_keeps_unset_secrets_distinguishable():
    assert redact_config({"api_key": ""})["api_key"] == ""


@pytest.mark.parametrize(
    "payload",
    [
        {"ssh_port": 0},
        {"ssh_port": 70000},
        {"ap_psk": "short"},
        {"api_endpoint": "gateway.example.net"},
    ],
)
def test_settings_reject_invalid_values(payload):
    with pytest.raises(ValueError):
        CameraProvisionSettings(**payload)


def test_settings_serialise_booleans_as_shell_flags():
    entries = CameraProvisionSettings(ap_always=True).to_config_entries()

    assert entries == {"ap_always": "1"}
    assert CameraProvisionSettings(ap_always=False).to_config_entries() == {
        "ap_always": "0"
    }


def test_settings_omit_untouched_fields():
    assert CameraProvisionSettings().to_config_entries() == {}


def test_on_camera_payload_pushes_preview_after_wifi_connects():
    apply = load_payload()["camcontrol-apply.sh"].decode()
    boot = load_payload()["camcontrol-boot.sh"].decode()

    assert "push-snapshot" in apply
    assert "camcontrol-apply.sh\" push" in boot
    assert apply.count("--no-check-certificate") == 2
    assert apply.count("X-Camera-Key") == 2


def test_probe_reports_capabilities_and_issues():
    client = _FakeSSHClient(
        {
            "command -v": (
                b"tool dropbear 1\ntool wpa_supplicant 1\ntool wpa_cli 1\n"
                b"tool nc 1\ntool base64 0\ntool ifconfig 1\ntool wget 1\n"
                b"tool chpasswd 1\n"
                b"iface wlan0\npersist 1\ninstalled 1\n"
                b"hook /home/yi-hack-v3/startup.sh\n"
            )
        }
    )

    capabilities = _provisioner(client).probe()

    assert capabilities.package_installed is True
    assert capabilities.wifi_interface == "wlan0"
    assert capabilities.can_host_ap is True
    # nc alone is not enough: the portal's basic auth needs base64.
    assert capabilities.can_serve_portal is False
    assert capabilities.boot_hook_candidates == ("/home/yi-hack-v3/startup.sh",)
    assert any(
        "portal cannot be served" in issue
        for issue in capabilities.blocking_issues
    )
    assert client.closed is True


def test_probe_flags_read_only_firmware_as_blocking():
    client = _FakeSSHClient({"command -v": b"persist 0\ninstalled 0\n"})

    capabilities = _provisioner(client).probe()

    assert capabilities.persistent_dir_writable is False
    assert any(
        "not writable" in issue for issue in capabilities.blocking_issues
    )
    assert any(
        "setup access point" in issue for issue in capabilities.blocking_issues
    )

def test_install_uploads_the_whole_payload_and_runs_the_installer():
    client = _FakeSSHClient({"install.sh": b"camcontrol-install: install complete\n"})

    log = _provisioner(client).install()

    for name in load_payload():
        assert f"/tmp/camcontrol-install/{name}" in client.uploads
    assert client.uploads["/tmp/camcontrol-install/install.sh"].startswith(b"#!/bin/sh")
    assert "install complete" in log
    assert any("install.sh" in command for command in client.commands)


def test_write_config_merges_into_the_existing_remote_file():
    client = _FakeSSHClient(
        {f"cat {CAMCONTROL_DIR}": b"ssh_port=22\nwifi_psk=stored\nap_always=0\n"}
    )

    merged = _provisioner(client).write_config(
        CameraProvisionSettings(ssh_port=2222, wifi_psk="", ap_always=True)
    )

    assert merged["ssh_port"] == "2222"
    assert merged["wifi_psk"] == "stored"
    assert merged["ap_always"] == "1"
    uploaded = client.uploads[f"{CAMCONTROL_DIR}/camcontrol.conf"].decode()
    assert "ssh_port=2222" in uploaded
    assert any("chmod 600" in command for command in client.commands)


def test_write_config_requires_the_package_to_be_installed():
    class _MissingClient(_FakeSSHClient):
        def exec_command(self, command: str, timeout: int = 0):
            stdin, stdout, stderr = super().exec_command(command, timeout)
            if command.startswith("cat "):
                stdout.channel = _FakeChannel(1)
            return stdin, stdout, stderr

    provisioner = _provisioner(_MissingClient())

    with pytest.raises(Exception, match="not installed"):
        provisioner.write_config(CameraProvisionSettings(ssh_port=22))


def test_reboot_is_not_detached_so_it_cannot_be_sighupped():
    client = _FakeSSHClient()

    _provisioner(client).reboot()

    # `(sleep 2; reboot) &` was silently cancelled when the SSH session
    # closed, and a bare `reboot` is not on the default PATH=/usr/bin:/bin.
    assert len(client.commands) == 1
    command = client.commands[0]
    assert command.endswith("reboot")
    assert "&" not in command
    assert "/home/base/tools" in command


def test_portal_reboots_after_responding_rather_than_in_background():
    body = load_payload()["camcontrol-httpd.sh"].decode()

    assert "(sleep 3; cc_tool reboot)" not in body
    assert body.index("cc_render_page\n") < body.index('CC_REBOOT" = "1"')


def test_sd_card_bundle_writes_payload_and_settings(tmp_path):
    build_sd_card_bundle(
        tmp_path, CameraProvisionSettings(wifi_ssid="HomeNet", ssh_port=2222)
    )

    assert (tmp_path / "camcontrol.conf").exists()
    assert (tmp_path / "CAMCONTROL-README.txt").exists()
    assert (tmp_path / "camcontrol-install" / "install.sh").exists()
    card_conf = (tmp_path / "camcontrol.conf").read_text()
    assert "wifi_ssid=HomeNet" in card_conf
    assert "ssh_port=2222" in card_conf


def test_sd_card_bundle_without_settings_writes_no_credentials(tmp_path):
    build_sd_card_bundle(tmp_path)

    assert not (tmp_path / "camcontrol.conf").exists()
    assert (tmp_path / "camcontrol-install" / "camcontrol.conf").exists()
