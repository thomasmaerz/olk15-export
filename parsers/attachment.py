# parsers/attachment.py
from __future__ import annotations
import base64, logging, re
from parsers.tnef import is_tnef, unpack_tnef
from email.header import decode_header
from urllib.parse import unquote

log = logging.getLogger("extract_outlook.attachment")


def _decode_filename(raw: str) -> str:
    """Decode RFC 2047 encoded-words and RFC 5987 percent-encoded filenames."""
    raw = raw.strip().strip('"')

    # Try RFC 5987: charset''percent-encoded
    if "''" in raw:
        parts = raw.split("''", 1)
        if len(parts) == 2:
            try:
                return unquote(parts[1], encoding=parts[0] or "utf-8")
            except Exception:
                pass

    # Try RFC 2047: =?charset?encoding?text?=
    if "=?" in raw:
        try:
            decoded_parts = decode_header(raw)
            result = []
            for part, charset in decoded_parts:
                if isinstance(part, bytes):
                    result.append(part.decode(charset or "utf-8", errors="replace"))
                else:
                    result.append(part)
            decoded = "".join(result)
            return decoded
        except Exception:
            pass

    return raw

def _make_rfc822_filename(body: bytes, fallback: str) -> str:
    """Extract Subject from forwarded email body to create useful filename."""
    try:
        body_str = body.decode("utf-8", errors="replace")
    except Exception:
        return fallback

    for line in body_str.splitlines():
        if line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            if subject:
                slug = re.sub(r"[^a-z0-9]+", "-", subject.lower().strip("-"))
                if len(slug) > 50:
                    slug = slug[:50].rstrip("-")
                return f"forwarded_{slug}.eml"

    return fallback if fallback != "attachment" else "forwarded_message.eml"

def parse_attachment(data: bytes) -> list[tuple[str, str, bytes]] | tuple[None, str] | None:
    """
    Parse .olk15MsgAttachment file.
    Returns list of (filename, content_type, decoded_bytes) on success.
    Returns (None, reason_str) on failure for diagnostics.
    Returns None only for truly empty/invalid input.
    For TNEF attachments, returns multiple tuples (one per extracted file).
    For regular attachments, returns a single-element list.
    """
    if not data or len(data) < 16:
        return None

    idx = data.lower().find(b"content-type:")
    if idx < 0:
        return (None, "no Content-Type header")
    mime_section = data[idx:]

    header_start = mime_section.lower().find(b"content-type:")
    if header_start < 0:
        return (None, "no Content-Type header")

    body_sep = re.search(rb"(\r\n\r\n|\n\n|\r\r)", mime_section[header_start:])
    if not body_sep:
        return (None, "no header/body separator")

    sep_start = header_start + body_sep.start()
    sep_end = header_start + body_sep.end()

    headers_raw = mime_section[header_start:sep_start]
    body_raw = mime_section[sep_end:]

    headers_text = headers_raw.replace(b"\r\n", b"\r").replace(b"\n", b"\r")
    headers_text = headers_text.replace(b"\r\t", b" ").replace(b"\r ", b" ")
    header_lines = headers_text.split(b"\r")


    content_type = ""
    filename = ""
    encoding = "base64"
    has_cte_header = False

    for line in header_lines:
        line_s = line.decode("ascii", errors="replace")
        low = line_s.lower()
        if low.startswith("content-type:"):
            parts = line_s.split(";")
            content_type = parts[0].split(":", 1)[1].strip()
            for p in parts[1:]:
                p = p.strip()
                if p.lower().startswith("name*="):
                    filename = _decode_filename(p.split("=", 1)[1].strip().strip('"'))
                elif p.lower().startswith("name="):
                    filename = _decode_filename(p.split("=", 1)[1].strip().strip('"'))
        elif low.startswith("content-disposition:"):
            for p in line_s.split(";")[1:]:
                p = p.strip()
                if p.lower().startswith("filename*="):
                    filename = _decode_filename(p.split("=", 1)[1].strip().strip('"'))
                elif p.lower().startswith("filename="):
                    filename = _decode_filename(p.split("=", 1)[1].strip().strip('"'))
        elif low.startswith("content-transfer-encoding:"):
            encoding = line_s.split(":", 1)[1].strip().lower()
            has_cte_header = True

    if not filename:
        filename = "attachment"

    if content_type.startswith("message/") and not has_cte_header:
        filename = _make_rfc822_filename(body_raw, filename)
        decoded = body_raw
        if is_tnef(filename=filename, content_type=content_type, data=decoded):
            extracted = unpack_tnef(decoded)
            if extracted:
                return extracted
        return [(filename, content_type, decoded)]
    elif encoding == "base64":
        try:
            clean_body = re.sub(rb"\s+", b"", body_raw)
            
            valid_chars = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
            if not all(c in valid_chars for c in clean_body):
                raise ValueError("invalid base64 characters")
            
            parts = [p for p in clean_body.split(b"=") if p]
            decoded_parts = []
            for p in parts:
                missing_padding = len(p) % 4
                if missing_padding:
                    p += b"=" * (4 - missing_padding)
                decoded_parts.append(base64.b64decode(p))
            decoded = b"".join(decoded_parts)


        except Exception:
            log.warning(
                "attachment decode failed: content_type=%r encoding=%s body_preview=%r",
                content_type,
                encoding,
                body_raw[:80].hex() if body_raw else b"",
            )
            return (None, "base64 decode failed")
    else:
        decoded = body_raw

    if is_tnef(filename=filename, content_type=content_type, data=decoded):
        extracted = unpack_tnef(decoded)
        if extracted:
            return extracted
        return [(filename, content_type, decoded)]

    return [(filename, content_type, decoded)]
