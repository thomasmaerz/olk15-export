from __future__ import annotations
from parsers.common import fix_mime_integrity

MIME_MARKERS = [
    b"Received:", b"From:", b"Return-Path:",
    b"MIME-Version:", b"Date:", b"Subject:", b"Message-ID:",
]

def parse_source(data: bytes) -> bytes | None:
    """Strip binary prefix from .olk15MsgSource; return fixed MIME bytes or None."""
    best = len(data)
    for marker in MIME_MARKERS:
        idx = data.find(marker)
        if 0 <= idx < best:
            best = idx
    if best == len(data):
        return None
    
    mime = data[best:]
    return fix_mime_integrity(mime)

