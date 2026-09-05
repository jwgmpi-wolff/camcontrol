from camera_bridge.jpeg_extract import extract_jpeg


def test_extract_jpeg_finds_embedded_frame():
    header = b"\x00" * 32
    jpeg = b"\xff\xd8\xff" + b"fake-jpeg-body" + b"\xff\xd9"
    trailer = b"\x00" * 16
    buffer = header + jpeg + trailer

    result = extract_jpeg(buffer)

    assert result == jpeg


def test_extract_jpeg_returns_none_when_no_soi():
    buffer = b"\x00" * 64
    assert extract_jpeg(buffer) is None


def test_extract_jpeg_returns_none_when_no_eoi():
    buffer = b"\x00" * 16 + b"\xff\xd8\xff" + b"unterminated"
    assert extract_jpeg(buffer) is None


def test_extract_jpeg_picks_first_frame_when_multiple_present():
    first = b"\xff\xd8\xff" + b"first" + b"\xff\xd9"
    second = b"\xff\xd8\xff" + b"second" + b"\xff\xd9"
    buffer = b"\x00" * 8 + first + b"\x00" * 8 + second

    result = extract_jpeg(buffer)

    assert result == first
