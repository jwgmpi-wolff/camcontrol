"""Pure byte-scanning helper to pull a JPEG frame out of a raw memory-mapped
buffer, such as the third-party-firmware /tmp/view live preview buffer, which embeds a
single JPEG frame inside a larger fixed-size region without a documented
offset table.
"""

from __future__ import annotations

_SOI = b"\xff\xd8"
_SOS_MARKER = 0xDA
_EOI_MARKER = 0xD9
# Markers with no length field / payload that can legally appear stand-alone
# before the scan (TEM) or as restart markers inside scan data (RSTn).
_STANDALONE_MARKERS = {0x01, *range(0xD0, 0xD8)}


def _find_frame_end(buffer: bytes, start: int) -> int | None:
    """Walk real JPEG marker segments from the SOI at `start` to find the
    index of the matching EOI's 0xFF byte, or None if this SOI does not lead
    to a structurally complete, well-formed frame.

    This does a real marker walk (not a substring search for the next
    ``\\xff\\xd9``) because raw ``\\xff\\xd9`` byte pairs can occur by chance
    in unrelated bytes elsewhere in the buffer (e.g. leftover data from a
    previous frame), which a naive search would mistake for the frame end.
    """
    pos = start + 2  # past FFD8
    n = len(buffer)
    while pos + 1 < n:
        if buffer[pos] != 0xFF:
            return None  # expected a marker here; not a real JPEG stream
        marker = buffer[pos + 1]
        if marker == _EOI_MARKER:
            return pos
        if marker in _STANDALONE_MARKERS:
            pos += 2
            continue
        if pos + 3 >= n:
            return None
        seg_len = (buffer[pos + 2] << 8) | buffer[pos + 3]
        if seg_len < 2:
            return None
        pos += 2 + seg_len
        if marker == _SOS_MARKER:
            # Entropy-coded scan data: 0xFF is only a real marker if not
            # followed by a stuff byte (0x00) or a restart marker (RSTn).
            # Anything else (EOI, or the next scan in a progressive JPEG)
            # is left for the outer loop to interpret.
            while pos + 1 < n:
                if buffer[pos] == 0xFF:
                    nxt = buffer[pos + 1]
                    if nxt == 0x00 or (0xD0 <= nxt <= 0xD7):
                        pos += 2
                        continue
                    break
                pos += 1
            else:
                return None
    return None


def extract_jpeg(buffer: bytes) -> bytes | None:
    """Return the first complete, structurally valid JPEG (SOI..EOI) found in
    buffer, or None.
    """
    search_from = 0
    while True:
        start = buffer.find(_SOI, search_from)
        if start == -1:
            return None
        end = _find_frame_end(buffer, start)
        if end is not None:
            return buffer[start : end + 2]
        search_from = start + 1

