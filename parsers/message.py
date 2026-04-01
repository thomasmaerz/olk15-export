# parsers/message.py
from __future__ import annotations
import chardet
import re
import datetime
import mimetypes
from email.message import EmailMessage

def _clean_text(text: str) -> str:
    """Remove nulls and binary remnants."""
    return text.replace("\x00", "").strip()

def _truncate_body(text: str, subtype: str) -> str:
    """Remove Outlook trailing metadata."""
    if subtype == "html":
        end_idx = text.lower().rfind("</html>")
        if end_idx != -1:
            text = text[:end_idx + 7]
        else:
            end_idx = text.lower().rfind("</body>")
            if end_idx != -1:
                text = text[:end_idx + 7]
    elif subtype == "calendar" or "BEGIN:VCALENDAR" in text:
        end_idx = text.rfind("END:VCALENDAR")
        if end_idx != -1:
            text = text[:end_idx + 13]
            
    patterns = [
        r'\{"MessageCardSerialized":',
        r'15\.0\.0\.0',
        r'<\?xml version="1\.0" encoding="utf-16"\?>',
        r'AddressSet><Version>15\.0\.0\.0',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            text = text[:match.start()].strip()
    
    binary_start = re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]{3,}', text)
    if binary_start:
        text = text[:binary_start.start()].strip()
            
    return text

def _is_mostly_ascii(text: str) -> bool:
    """Check if a string is primarily ASCII characters."""
    if not text: return True
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return (ascii_chars / len(text)) > 0.7

def _robust_decode(data: bytes, hint_enc: str, trust_hint: bool = False) -> str:
    """Try to decode bytes. If trust_hint is True, do not try fallback encodings."""
    if trust_hint:
        try:
            return data.decode(hint_enc, errors="replace")
        except Exception:
            pass

    # If hint was utf-8/ascii, try it first and check if it's actually clean
    if hint_enc in ["utf-8", "ascii"]:
        try:
            text = data.decode("utf-8", errors="replace")
            # If it's clean ASCII (very few nulls), return it
            if text.count("\x00") < len(text) // 20:
                return text
        except Exception:
            pass

    # If it's very null-heavy, try unshifted UTF-16
    if data.count(b"\x00") > len(data) // 10:
        for e in ["utf-16-le", "utf-16-be"]:
            try:
                t = data.decode(e, errors="replace")
                if _is_mostly_ascii(t): return t
            except Exception:
                pass

    # Final fallback to chardet
    detection = chardet.detect(data)
    encoding = detection.get("encoding") or "utf-8"
    try:
        return data.decode(encoding, errors="replace")
    except Exception:
        return data.decode("utf-8", errors="replace")

def _find_body_start(data: bytes) -> tuple[int, str, bool]:
    """Find the earliest start of HTML, RTF, or Calendar body. Returns (pos, enc, trust)."""
    # Prioritize HTML markers
    html_markers = [
        (b"<html", "utf-8"),
        (b"<HTML", "utf-8"),
        (b"<\x00h\x00t\x00m\x00l", "utf-16-le"),
    ]
    for marker, enc in html_markers:
        pos = data.find(marker)
        if pos != -1:
            return pos, enc, True
            
    # Then RTF or Calendar
    other_markers = [
        (b"{\\rtf", "utf-8"),
        (b"BEGIN:VCALENDAR", "utf-8"),
        (b"{\x00\\\x00r\x00t\x00f", "utf-16-le"),
        (b"B\x00E\x00G\x00I\x00N\x00:\x00V\x00C\x00A\x00L", "utf-16-le"),
    ]
    for marker, enc in other_markers:
        pos = data.find(marker)
        if pos != -1:
            return pos, enc, True
                
    return -1, "utf-8", False

def parse_message(data: bytes, meta: dict | None = None, attachments: list[tuple[str, str, bytes]] | None = None) -> bytes | None:
    """Reconstruct email from binary .olk15Message using SQLite metadata."""
    pos, hint_enc, trust = _find_body_start(data)
    
    if pos == -1:
        idx = data.find(b"IPM.Note")
        if idx != -1:
            pos = idx + 8
            while pos < len(data) and data[pos] < 32 and data[pos] != 0:
                pos += 1
        else:
            pos = min(1024, len(data))
        hint_enc = "utf-8"
        trust = False

    body_bytes = data[pos:]
    body_text = _robust_decode(body_bytes, hint_enc, trust)
    body_text = _clean_text(body_text)
    
    is_calendar = "BEGIN:VCALENDAR" in body_text
    is_html = "<html>" in body_text.lower() or "<body" in body_text.lower() or "<div" in body_text.lower()
    is_rtf = body_text.startswith("{\\rtf")
    
    subtype = "plain"
    if is_calendar: subtype = "calendar"
    elif is_html: subtype = "html"
    elif is_rtf: subtype = "rtf"
    
    body_text = _truncate_body(body_text, subtype)
    
    msg = EmailMessage()
    if meta:
        if meta.get("from"): msg["From"] = meta["from"]
        if meta.get("to"): msg["To"] = meta["to"]
        if meta.get("cc"): msg["Cc"] = meta["cc"]
        if meta.get("subject"): msg["Subject"] = meta["subject"]
        if meta.get("message_id"): msg["Message-ID"] = meta["message_id"]
        if meta.get("thread_id"): msg["X-Outlook-Thread-ID"] = str(meta["thread_id"])
        
        ts_received = meta.get("date", -1)
        ts_sent = meta.get("sent_date", -1)
        final_ts = ts_received if ts_received > 0 else ts_sent
            
        if final_ts > 0:
            try:
                if final_ts < 1000000000:
                    dt = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=final_ts)
                else:
                    dt = datetime.datetime.fromtimestamp(final_ts, tz=datetime.timezone.utc)
                msg["Date"] = dt.strftime("%a, %d %b %Y %H:%M:%S %z")
            except Exception:
                pass

    if subtype == "calendar":
        msg.set_content(body_text, charset="utf-8")
        msg.replace_header("Content-Type", "text/calendar; charset=utf-8")
    else:
        msg.set_content(body_text, subtype=subtype, charset="utf-8")
        
    if attachments:
        msg.make_mixed()
        for filename, content_type, att_data in attachments:
            if content_type is None:
                content_type, _ = mimetypes.guess_type(filename)
                if content_type is None: content_type = "application/octet-stream"
            
            # handle cases where guess_type might return a type without a slash, though rare
            if "/" in content_type:
                maintype, att_subtype = content_type.split("/", 1)
            else:
                maintype, att_subtype = "application", "octet-stream"
                
            msg.add_attachment(att_data, maintype=maintype, subtype=att_subtype, filename=filename)
    
    if "From" not in msg: msg["From"] = "unknown@localhost"
    if "Subject" not in msg: msg["Subject"] = "(No Subject)"
    if "Date" not in msg: msg["Date"] = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")

    return msg.as_bytes()
