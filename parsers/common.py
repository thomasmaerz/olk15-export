# parsers/common.py
from __future__ import annotations
import email.policy
from email.parser import BytesParser
import logging

log = logging.getLogger(__name__)

def fix_mime_integrity(mime: bytes) -> bytes:
    """Normalize line endings and ensure valid MIME structure."""
    # Normalize bare CR to CRLF
    mime = mime.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    mime = mime.replace(b"\n", b"\r\n")
    
    try:
        # Use compat32 for leniency on existing headers
        msg = BytesParser(policy=email.policy.compat32).parsebytes(mime)
        return msg.as_bytes()
    except Exception as e:
        log.debug("MIME integrity fix failed: %s", e)
        return mime
