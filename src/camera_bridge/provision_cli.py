"""Configuration tool for the on-camera CamControl package.

    python -m camera_bridge.provision_cli probe    --camera front-door
    python -m camera_bridge.provision_cli install  --camera front-door
    python -m camera_bridge.provision_cli show     --camera front-door
    python -m camera_bridge.provision_cli set      --camera front-door \
        --ssh-port 22 --wifi-ssid HomeNet --set-wifi-psk --reboot
    python -m camera_bridge.provision_cli sdcard   --out E:\\

Secrets are never taken from argv (process arguments are readable by other
users); the --set-* flags prompt instead, or read the matching CAMCONTROL_*
environment variable for unattended runs.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from .camera_provision import (
    CameraProvisionError,
    CameraProvisioner,
    CameraProvisionSettings,
    build_sd_card_bundle,
    redact_config,
)
from .config import DEFAULT_CONFIG_PATH, load_config
from .models import Hi3518eSshCameraConfig

_SECRET_PROMPTS = {
    "wifi_psk": ("--set-wifi-psk", "CAMCONTROL_WIFI_PSK", "Wi-Fi password"),
    "admin_password": (
        "--set-admin-password",
        "CAMCONTROL_ADMIN_PASSWORD",
        "Camera login password",
    ),
    "api_key": ("--set-api-key", "CAMCONTROL_API_KEY", "Gateway API key"),
    "ap_psk": ("--set-ap-psk", "CAMCONTROL_AP_PSK", "Setup AP password"),
}


def _find_camera(camera_id: str, config_path: Path) -> Hi3518eSshCameraConfig:
    config = load_config(config_path)
    for camera in config.cameras:
        if camera.id == camera_id:
            if not isinstance(camera, Hi3518eSshCameraConfig):
                raise SystemExit(f"Camera {camera_id!r} is not a Hi3518e SSH camera")
            return camera
    known = ", ".join(c.id for c in config.cameras) or "none configured"
    raise SystemExit(f"Unknown camera id {camera_id!r}. Known ids: {known}")


def _collect_secret(field: str) -> str | None:
    _flag, env_var, prompt = _SECRET_PROMPTS[field]
    from_env = os.environ.get(env_var)
    if from_env:
        return from_env
    value = getpass.getpass(f"{prompt}: ")
    return value or None


def _build_settings(args: argparse.Namespace) -> CameraProvisionSettings:
    payload: dict[str, object] = {}
    for field in (
        "ssh_port",
        "wifi_ssid",
        "admin_user",
        "api_endpoint",
        "camera_id",
        "push_interval_seconds",
        "ap_ssid",
        "portal_port",
        "ap_timeout_seconds",
        "wifi_wait_seconds",
    ):
        value = getattr(args, field, None)
        if value is not None:
            payload[field] = value
    if args.ap_always is not None:
        payload["ap_always"] = args.ap_always
    for field in _SECRET_PROMPTS:
        if getattr(args, f"set_{field}", False):
            secret = _collect_secret(field)
            if secret:
                payload[field] = secret
    try:
        return CameraProvisionSettings(**payload)
    except ValueError as exc:
        raise SystemExit(f"Invalid settings: {exc}") from exc


def _print_mapping(title: str, mapping: dict) -> None:
    print(title)
    for key in sorted(mapping):
        print(f"  {key}: {mapping[key]}")


def _cmd_probe(args: argparse.Namespace) -> int:
    camera = _find_camera(args.camera, args.config)
    capabilities = CameraProvisioner(camera).probe()
    print(f"camera: {camera.id} ({camera.name})")
    print(f"package installed: {capabilities.package_installed}")
    print(f"wifi interface: {capabilities.wifi_interface}")
    print(f"can host setup AP: {capabilities.can_host_ap}")
    print(f"can serve portal: {capabilities.can_serve_portal}")
    _print_mapping("tools:", capabilities.tools)
    if capabilities.boot_hook_candidates:
        print("boot hook candidates:")
        for path in capabilities.boot_hook_candidates:
            print(f"  {path}")
    if capabilities.blocking_issues:
        print("issues:")
        for issue in capabilities.blocking_issues:
            print(f"  - {issue}")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    camera = _find_camera(args.camera, args.config)
    print(CameraProvisioner(camera).install())
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    camera = _find_camera(args.camera, args.config)
    settings = CameraProvisioner(camera).read_config()
    _print_mapping(f"{camera.id} on-camera settings:", redact_config(settings))
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    camera = _find_camera(args.camera, args.config)
    settings = _build_settings(args)
    if not settings.to_config_entries():
        raise SystemExit("Nothing to change; pass at least one setting flag.")
    provisioner = CameraProvisioner(camera)
    merged = provisioner.write_config(settings)
    _print_mapping("saved:", redact_config(merged))
    if args.reboot:
        provisioner.reboot()
        print("camera is rebooting; settings apply on boot")
    else:
        print("reboot the camera to apply these settings")
    return 0


def _cmd_reboot(args: argparse.Namespace) -> int:
    camera = _find_camera(args.camera, args.config)
    CameraProvisioner(camera).reboot()
    print("camera is rebooting")
    return 0


def _cmd_sdcard(args: argparse.Namespace) -> int:
    settings = _build_settings(args) if args.with_settings else None
    written = build_sd_card_bundle(args.out, settings)
    print(f"wrote {len(written)} files to {args.out}")
    if settings is not None:
        print("camcontrol.conf contains credentials -- erase the card after use")
    return 0


def _add_camera_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--camera", required=True, help="camera id from cameras.json")


def _add_setting_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ssh-port", type=int, dest="ssh_port")
    parser.add_argument("--wifi-ssid", dest="wifi_ssid")
    parser.add_argument("--admin-user", dest="admin_user")
    parser.add_argument("--api-endpoint", dest="api_endpoint")
    parser.add_argument("--camera-id", dest="camera_id")
    parser.add_argument("--push-interval-seconds", type=int, dest="push_interval_seconds")
    parser.add_argument("--ap-ssid", dest="ap_ssid")
    parser.add_argument("--portal-port", type=int, dest="portal_port")
    parser.add_argument("--ap-timeout-seconds", type=int, dest="ap_timeout_seconds")
    parser.add_argument("--wifi-wait-seconds", type=int, dest="wifi_wait_seconds")
    parser.add_argument(
        "--ap-always",
        dest="ap_always",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="keep the setup AP up at every boot",
    )
    for field, (flag, env_var, prompt) in _SECRET_PROMPTS.items():
        parser.add_argument(
            flag,
            dest=f"set_{field}",
            action="store_true",
            help=f"set the {prompt.lower()} (prompts, or reads ${env_var})",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="camera_bridge.provision_cli",
        description="Configure the on-camera CamControl package.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="path to cameras.json",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="report what the camera firmware supports")
    _add_camera_arg(probe)
    probe.set_defaults(func=_cmd_probe)

    install = sub.add_parser("install", help="install the on-camera package")
    _add_camera_arg(install)
    install.set_defaults(func=_cmd_install)

    show = sub.add_parser("show", help="show stored settings (secrets redacted)")
    _add_camera_arg(show)
    show.set_defaults(func=_cmd_show)

    setter = sub.add_parser("set", help="change settings on the camera")
    _add_camera_arg(setter)
    _add_setting_args(setter)
    setter.add_argument("--reboot", action="store_true", help="reboot to apply")
    setter.set_defaults(func=_cmd_set)

    reboot = sub.add_parser("reboot", help="reboot the camera")
    _add_camera_arg(reboot)
    reboot.set_defaults(func=_cmd_reboot)

    sdcard = sub.add_parser("sdcard", help="write the SD-card recovery bundle")
    sdcard.add_argument("--out", type=Path, required=True, help="card root directory")
    sdcard.add_argument(
        "--with-settings",
        action="store_true",
        help="also write camcontrol.conf from the setting flags",
    )
    _add_setting_args(sdcard)
    sdcard.set_defaults(func=_cmd_sdcard)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CameraProvisionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
