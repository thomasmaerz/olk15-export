# parsers/attachment.py
from __future__ import annotations
import base64, re
from parsers.tnef import is_tnef, unpack_tnef
from email.header import decode_header
from urllib.parse import unquote


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

def parse_attachment(data: bytes) -> list[tuple[str, str, bytes]] | None:
    """
    Parse .olk15MsgAttachment file.
    Returns list of (filename, content_type, decoded_bytes) or None if unparseable.
    For TNEF attachments, returns multiple tuples (one per extracted file).
    For regular attachments, returns a single-element list.
    """
    # Find MIME headers start
    idx = data.lower().find(b"content-type:")
    if idx < 0:
        return None
    mime_section = data[idx:]

    # Find the start of headers
    header_start = mime_section.find(b"Content-Type:")
    if header_start < 0:
        header_start = mime_section.find(b"content-type:")
    
    # Debug
    # print(f"DEBUG: mime_section={mime_section!r}")
    
    # Find the start of headers
    header_start = mime_section.lower().find(b"content-type:")
    if header_start < 0:
        return None
    
    # Headers end at the first double-newline
    body_sep = re.search(rb"(\r\n\r\n|\n\n|\r\r)", mime_section[header_start:])
    if not body_sep:
        return None
    
    sep_start = header_start + body_sep.start()
    sep_end = header_start + body_sep.end()
    
    headers_raw = mime_section[header_start:sep_start]
    body_raw = mime_section[sep_end:]
    
    # Normalize headers for parsing
    headers_text = headers_raw.replace(b"\r\n", b"\r").replace(b"\n", b"\r")
    headers_text = headers_text.replace(b"\r\t", b" ").replace(b"\r ", b" ")
    header_lines = headers_text.split(b"\r")


    content_type = ""
    filename = ""
    encoding = "base64"

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

    if not filename:
        filename = "attachment"

    if encoding == "base64":
        try:
            # Outlook sometimes splits base64 blocks with '=' and newlines
            # We must join them correctly.
            
            # The most robust way to decode concatenated base64 is to split by '=' 
            # and decode each chunk, or just find each 4-char block.
            # But usually, it's just a single blob that might have been split.
            
            # Remove all whitespace characters
            clean_body = re.sub(rb"\s+", b"", body_raw)
            
            # Split by '=' and decode each non-empty part
            parts = [p for p in clean_body.split(b"=") if p]
            decoded_parts = []
            for p in parts:
                # Add back required padding for this specific part
                missing_padding = len(p) % 4
                if missing_padding:
                    p += b"=" * (4 - missing_padding)
                decoded_parts.append(base64.b64decode(p))
            decoded = b"".join(decoded_parts)


        except Exception:
            return None
    else:
        decoded = body_raw

    if is_tnef(filename=filename, content_type=content_type, data=decoded):
        extracted = unpack_tnef(decoded)
        if extracted:
            return extracted
        return [(filename, content_type, decoded)]

    return [(filename, content_type, decoded)]
