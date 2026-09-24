"""Convert and play short voice messages through Hi3518e camera speakers."""

from __future__ import annotations

import shlex
import subprocess
import threading
import uuid

import paramiko

from .models import Hi3518eSshCameraConfig

MAX_VOICE_MESSAGE_BYTES = 5 * 1024 * 1024
MAX_VOICE_MESSAGE_SECONDS = 30

_CAMERA_LIBRARY_PATH = (
    "/home/lib:/home/app/locallib:/home/hisiko/hisilib:/home/libusr"
)


class VoiceMessageError(RuntimeError):
    pass


def convert_to_camera_aac(data: bytes, ffmpeg_path: str = "ffmpeg") -> bytes:
    if not data:
        raise VoiceMessageError("Voice message is empty")
    if len(data) > MAX_VOICE_MESSAGE_BYTES:
        raise VoiceMessageError("Voice message exceeds the 5 MB limit")

    try:
        result = subprocess.run(
            [
                ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                "-t",
                str(MAX_VOICE_MESSAGE_SECONDS),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "aac",
                "-b:a",
                "24k",
                "-f",
                "adts",
                "pipe:1",
            ],
            input=data,
            capture_output=True,
            check=False,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VoiceMessageError(f"Audio conversion failed: {exc}") from exc

    if result.returncode != 0 or not result.stdout:
        detail = result.stderr.decode(errors="replace").strip()
        raise VoiceMessageError(f"Audio conversion failed: {detail or 'no output'}")
    return result.stdout


class VoiceMessagePlayer:
    def __init__(self, config: Hi3518eSshCameraConfig) -> None:
        self._config = config
        self._lock = threading.Lock()

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

    def play(self, source_audio: bytes) -> None:
        aac = convert_to_camera_aac(source_audio)
        remote_path = f"/tmp/camcontrol-voice-{uuid.uuid4().hex}.aac"
        quoted_path = shlex.quote(remote_path)

        with self._lock:
            client = self._connect()
            try:
                stdin, stdout, stderr = client.exec_command(
                    f"cat > {quoted_path}", timeout=15
                )
                stdin.write(aac)
                stdin.channel.shutdown_write()
                stdout.channel.settimeout(15)
                stdout.read()
                upload_error = stderr.read().decode(errors="replace").strip()
                if stdout.channel.recv_exit_status() != 0 or upload_error:
                    raise VoiceMessageError(
                        f"Camera audio upload failed: {upload_error or 'unknown error'}"
                    )

                command = (
                    f"export LD_LIBRARY_PATH={_CAMERA_LIBRARY_PATH}; "
                    f"/home/app/rmm {quoted_path} 1 >/dev/null 2>&1 & "
                    "pid=$!; sleep 31; kill $pid 2>/dev/null; "
                    "wait $pid 2>/dev/null; "
                    f"rm -f {quoted_path}"
                )
                _stdin, stdout, stderr = client.exec_command(command, timeout=40)
                stdout.channel.settimeout(40)
                stdout.read()
                playback_error = stderr.read().decode(errors="replace").strip()
                if stdout.channel.recv_exit_status() != 0 or playback_error:
                    raise VoiceMessageError(
                        f"Camera playback failed: {playback_error or 'unknown error'}"
                    )
            except VoiceMessageError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise VoiceMessageError(
                    f"Cannot play voice message on {self._config.host}: {exc}"
                ) from exc
            finally:
                try:
                    client.exec_command(f"rm -f {quoted_path}", timeout=5)
                except Exception:  # noqa: BLE001
                    pass
                client.close()