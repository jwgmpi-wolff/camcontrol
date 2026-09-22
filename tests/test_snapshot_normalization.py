from camera_bridge.api import _complete_jpeg


def test_complete_jpeg_appends_missing_eoi_marker():
    assert _complete_jpeg(b"\xff\xd8camera-frame") == b"\xff\xd8camera-frame\xff\xd9"


def test_complete_jpeg_preserves_complete_and_non_jpeg_payloads():
    complete = b"\xff\xd8camera-frame\xff\xd9"

    assert _complete_jpeg(complete) == complete
    assert _complete_jpeg(b"h264-frame") == b"h264-frame"