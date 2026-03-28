#!/usr/bin/env python3
"""Rebuild all_emails.mbox from existing .eml files with correct From_ lines."""
import csv, datetime, pathlib, re, sys
from email.parser import BytesParser

OUTPUT = pathlib.Path(__file__).parent / "output"
MBX_PATH = OUTPUT / "all_emails.mbox"
CSV_PATH = OUTPUT / "summary.csv"

def extract_sender(mime_bytes: bytes) -> str:
    try:
        msg = BytesParser().parsebytes(mime_bytes)
        raw = msg.get("From", "")
        m = re.search(r'<([^>]+)>', raw)
        if m:
            return m.group(1)
        m = re.search(r'[\w.+-]+@[\w.-]+', raw)
        if m:
            return m.group(0)
    except Exception:
        pass
    return "unknown@localhost"

def make_from_line(sender: str) -> bytes:
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%a %b %d %H:%M:%S %Y")
    return f"From {sender} {ts}\n".encode()

def main():
    seen_ids, total, written, skipped_dup, skipped_err = set(), 0, 0, 0, 0
    
    eml_files = []
    for subdir in ["messages", "sources"]:
        d = OUTPUT / subdir
        if d.exists():
            eml_files.extend(d.glob("*.eml"))
    print(f"Found {len(eml_files)} .eml files")
    
    MBX_PATH.write_bytes(b"")
    with open(MBX_PATH, "ab") as mbox:
        for path in sorted(eml_files):
            total += 1
            if total % 5000 == 0:
                print(f"  {total}/{len(eml_files)} (written={written}, dup={skipped_dup}, err={skipped_err})")
            try:
                mime = path.read_bytes()
                if b"MAILER-DAEMON" in mime:
                    skipped_err += 1
                    continue
                msg = BytesParser().parsebytes(mime)
                mid = (msg.get("Message-ID") or "").strip()
                # If already seen during this run OR in initial CSV, skip
                if mid and mid in seen_ids:
                    skipped_dup += 1
                    continue
                if mid:
                    seen_ids.add(mid)
                sender = extract_sender(mime)
                mbox.write(make_from_line(sender))
                mbox.write(mime)
                mbox.write(b"\n")
                written += 1
            except Exception as exc:
                skipped_err += 1
                print(f"  ERROR {path.name}: {exc}", file=sys.stderr)
    print(f"Done: {written} written, {skipped_dup} dup, {skipped_err} err -> {MBX_PATH}")
    print("MBOX_REBUILD_FINISHED_SUCCESSFULLY")

if __name__ == "__main__":
    main()
