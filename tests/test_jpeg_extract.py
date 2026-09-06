from camera_bridge.jpeg_extract import extract_jpeg


def _make_jpeg(scan_data: bytes = b"\x01\xff\x00\x02\xff\xd0\x03") -> bytes:
    """A minimal but structurally valid single-scan JPEG: SOI, one APP0
    segment, one SOS segment, entropy-coded scan data (including a stuffed
    0xFF00 and a restart marker to exercise that handling), then EOI.
    """
    soi = b"\xff\xd8"
    app0 = b"\xff\xe0" + (2 + 4).to_bytes(2, "big") + b"JFIF"
    sos = b"\xff\xda" + (2 + 2).to_bytes(2, "big") + b"\x00\x00"
    eoi = b"\xff\xd9"
    return soi + app0 + sos + scan_data + eoi


def test_extract_jpeg_finds_embedded_frame():
    header = b"\x00" * 32
    jpeg = _make_jpeg()
    trailer = b"\x00" * 16
    buffer = header + jpeg + trailer

    result = extract_jpeg(buffer)

    assert result == jpeg


def test_extract_jpeg_returns_none_when_no_soi():
    buffer = b"\x00" * 64
    assert extract_jpeg(buffer) is None


def test_extract_jpeg_returns_none_when_no_eoi():
    buffer = b"\x00" * 16 + b"\xff\xd8\xff\xe0\x00\x06JFIF" + b"unterminated"
    assert extract_jpeg(buffer) is None


def test_extract_jpeg_picks_first_frame_when_multiple_present():
    first = _make_jpeg(b"first-scan-bytes")
    second = _make_jpeg(b"second-scan-bytes")
    buffer = b"\x00" * 8 + first + b"\x00" * 8 + second

    result = extract_jpeg(buffer)

    assert result == first


def test_extract_jpeg_skips_spurious_soi_in_noise():
    # A coincidental FFD8 byte pair followed by non-marker garbage (as can
    # happen in leftover/unrelated bytes of a large mmap buffer) must not be
    # mistaken for a real frame start; the real frame later in the buffer
    # should still be found.
    spurious = b"\xff\xd8\xff\x4c\xa7\xd9\x8c\x39\x62\x37"
    real = _make_jpeg()
    buffer = spurious + b"\x00" * 8 + real

    result = extract_jpeg(buffer)

    assert result == real
