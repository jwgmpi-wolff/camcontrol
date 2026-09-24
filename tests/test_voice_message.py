from __future__ import annotations

import subprocess

import pytest

from camera_bridge.voice_message import VoiceMessageError, convert_to_camera_aac


def test_convert_to_camera_aac_uses_validated_camera_format(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout=b"aac", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert convert_to_camera_aac(b"source") == b"aac"
    command = captured["command"]
    assert isinstance(command, list)
    assert command[command.index("-ar") + 1] == "16000"
    assert command[command.index("-ac") + 1] == "1"
    assert command[command.index("-f") + 1] == "adts"


def test_convert_to_camera_aac_rejects_empty_message():
    with pytest.raises(VoiceMessageError, match="empty"):
        convert_to_camera_aac(b"")