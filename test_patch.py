import pathlib, re, sys

def extract_clean_eml(content: bytes) -> bytes:
    # 1. Find the last known header line to define header block
    # Standard headers we expect
    header_markers = [b"Received:", b"From:", b"To:", b"Subject:", b"Date:", b"Message-ID:", b"MIME-Version:", b"Return-Path:"]
    
    last_header_pos = 0
    for marker in header_markers:
        pos = content.rfind(marker)
        if pos != -1:
            # Find end of this line
            line_end = content.find(b"\n", pos)
            if line_end != -1:
                last_header_pos = max(last_header_pos, line_end + 1)

    headers = content[:last_header_pos].strip()
    
    # 2. Find body start
    # Try UTF-16 HTML
    idx_u16 = content.find(b"<\x00h\x00t\x00m\x00l")
    if idx_u16 != -1:
        try:
            body = content[idx_u16:].decode("utf-16-le", errors="replace")
            return headers + b"\r\nContent-Type: text/html; charset=\"utf-8\"\r\nMIME-Version: 1.0\r\n\r\n" + body.encode("utf-8")
        except Exception:
            pass

    # Try UTF-8 HTML
    idx_u8 = content.find(b"<html")
    if idx_u8 != -1:
        body = content[idx_u8:]
        return headers + b"\r\nContent-Type: text/html; charset=\"utf-8\"\r\nMIME-Version: 1.0\r\n\r\n" + body

    # Fallback: Just take everything after headers
    body = content[last_header_pos:].strip()
    return headers + b"\r\nContent-Type: text/plain; charset=\"utf-8\"\r\nMIME-Version: 1.0\r\n\r\n" + body

# Test on a known UTF-16 file
p = pathlib.Path('/Users/thomasmaerz/olk15-export/output/messages/0000FBA7-B8C6-4B06-B554-3B004DA5201F.eml')
if p.exists():
    res = extract_clean_eml(p.read_bytes())
    print("--- HEADERS ---")
    print(res[:500].decode("utf-8", errors="replace"))
    print("--- BODY START ---")
    body_start = res.find(b"\r\n\r\n") + 4
    print(res[body_start:body_start+200].decode("utf-8", errors="replace"))
