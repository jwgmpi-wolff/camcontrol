from __future__ import annotations

from unittest.mock import MagicMock, patch

from camera_bridge.camera_discovery import CameraDiscovery


def _capture(opened: bool) -> MagicMock:
    capture = MagicMock()
    capture.isOpened.return_value = opened
    capture.get.side_effect = lambda prop: {
        3: 1280.0,
        4: 720.0,
        5: 30.0,
        6: float(int.from_bytes(b"MJPG", "little")),
    }.get(prop, 0.0)
    return capture


@patch("camera_bridge.camera_discovery.platform.system", return_value="Linux")
@patch("camera_bridge.camera_discovery.glob.glob", return_value=[])
def test_no_camera_returns_empty(_glob: MagicMock, _system: MagicMock) -> None:
    assert CameraDiscovery().discover() == []


@patch("camera_bridge.camera_discovery.shutil.which", return_value=None)
@patch("camera_bridge.camera_discovery.platform.system", return_value="Linux")
@patch("camera_bridge.camera_discovery.cv2.VideoCapture")
def test_probe_reports_uvc_capability(
    video_capture: MagicMock, _system: MagicMock, _which: MagicMock
) -> None:
    video_capture.return_value = _capture(True)

    device = CameraDiscovery().probe("/dev/video0")

    assert device.is_uvc_compatible is True
    assert device.capabilities[0].width == 1280
    assert device.capabilities[0].pixel_format == "MJPG"
    video_capture.return_value.release.assert_called_once()


@patch("camera_bridge.camera_discovery.shutil.which", return_value=None)
@patch("camera_bridge.camera_discovery.platform.system", return_value="Linux")
@patch("camera_bridge.camera_discovery.cv2.VideoCapture")
def test_incompatible_device_is_excluded(
    video_capture: MagicMock, _system: MagicMock, _which: MagicMock
) -> None:
    video_capture.return_value = _capture(False)

    assert CameraDiscovery().discover("/dev/video9") == []
    video_capture.return_value.release.assert_called_once()