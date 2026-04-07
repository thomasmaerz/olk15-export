# parsers/tnef.py
from __future__ import annotations

TNEF_CONTENT_TYPES = frozenset([
    "application/ms-tnef",
    "application/vnd.ms-tnef",
])

TNEF_FILENAMES = frozenset(["winmail.dat", "win.dat"])


def is_tnef(filename: str = "", content_type: str = "", data: bytes = b"") -> bool:
    """Check if an attachment is TNEF-encoded."""
    if filename.lower() in TNEF_FILENAMES:
        return True
    if content_type.lower() in TNEF_CONTENT_TYPES:
        return True
    if len(data) >= 4:
        import struct
        try:
            sig = struct.unpack("<I", data[:4])[0]
            if sig == 0x223E9F78:
                return True
        except Exception:
            pass
    return False


def unpack_tnef(data: bytes) -> list[tuple[str, str, bytes]]:
    """
    Unpack a TNEF (winmail.dat) blob and return extracted files.
    Returns list of (filename, content_type, decoded_bytes).
    Returns empty list if no file attachments are found inside.
    """
    from tnefparse import TNEF

    try:
        tnef = TNEF(data)
    except Exception:
        return []

    results: list[tuple[str, str, bytes]] = []
    for att in tnef.attachments:
        if not att.data:
            continue
        name = att.name or "Untitled Attachment"
        ct = "application/octet-stream"
        results.append((name, ct, att.data))

    if not results:
        return []

    return results
