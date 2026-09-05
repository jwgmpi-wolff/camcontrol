"""Pure byte-scanning helper to pull a JPEG frame out of a raw memory-mapped
buffer, such as the yi-hack-v3 /tmp/view live preview buffer, which embeds a
single JPEG frame inside a larger fixed-size region without a documented
offset table.
"""

from __future__ import annotations

SOI = b"\xff\xd8\xff"
EOI = b"\xff\xd9"


def extract_jpeg(buffer: bytes) -> bytes | None:
    """Return the first complete JPEG (SOI..EOI) found in buffer, or None."""
    start = buffer.find(SOI)
    if start == -1:
        return None
    end = buffer.find(EOI, start)
    if end == -1:
        return None
    return buffer[start : end + len(EOI)]
