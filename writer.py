from __future__ import annotations
import csv, email, email.policy, email.message, pathlib, logging, datetime, re, os, socket, unicodedata
from email.parser import BytesParser

log = logging.getLogger(__name__)

CSV_FIELDS = ["uuid", "source", "message_id", "from", "to", "subject", "date", "source_file"]


def _sanitize_filename(filename: str, existing: set[str] | None = None) -> str:
    """Make a filename safe for filesystem use."""
    filename = unicodedata.normalize("NFC", filename)
    filename = filename.strip()

    for ch in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
        filename = filename.replace(ch, "_")

    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        max_name = 200 - len(ext)
        if max_name < 1:
            ext = ext[:200] if len(ext) > 200 else ext
            max_name = 200 - len(ext)
        filename = name[:max_name] + ext

    if existing and filename in existing:
        name, ext = os.path.splitext(filename)
        counter = 1
        while f"{name}_{counter}{ext}" in existing:
            counter += 1
        filename = f"{name}_{counter}{ext}"

    return filename if filename else "attachment"

class EmlWriter:
    def __init__(self, output_dir: pathlib.Path):
        self.out = output_dir
        self.out.mkdir(parents=True, exist_ok=True)
        self._seen_ids: set[str] = set()
        
        # Initialize Maildir
        self.maildir_path = self.out / "Maildir"
        
        self._csv_path = self.out / "summary.csv"
        self._csv_file = open(self._csv_path, "w", newline="", encoding="utf-8")
        self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=CSV_FIELDS)
        self._csv_writer.writeheader()

    def write_eml(self, uuid: str, mime_bytes: bytes, source: str) -> bool:
        """Write MIME bytes as .eml file and add to Maildir. Returns False if duplicate Message-ID."""
        msg = None
        try:
            msg = BytesParser(policy=email.policy.compat32).parsebytes(mime_bytes)
        except Exception as exc:
            log.warning("Failed to parse MIME for %s, writing raw bytes: %s", uuid, exc)

        msg_id = ""
        if msg is not None:
            msg_id = (msg.get("Message-ID") or "").strip().strip("<>")
            if msg_id and msg_id in self._seen_ids:
                log.debug("Skipping duplicate Message-ID %s (uuid=%s)", msg_id, uuid)
                return False
            if msg_id:
                self._seen_ids.add(msg_id)
        else:
            for line in mime_bytes.split(b"\r\n")[:50]:
                if line.lower().startswith(b"message-id:"):
                    raw_id = line.split(b":", 1)[1].strip().decode("ascii", errors="replace")
                    msg_id = raw_id.strip("<> ")
                    if msg_id and msg_id in self._seen_ids:
                        log.debug("Skipping duplicate Message-ID %s (uuid=%s)", msg_id, uuid)
                        return False
                    if msg_id:
                        self._seen_ids.add(msg_id)
                    break

        # Add to Maildir
        try:
            cur_dir = self.maildir_path / "cur"
            cur_dir.mkdir(parents=True, exist_ok=True)
            import uuid as uuid_mod
            unique_name = f"{datetime.datetime.now().timestamp()}.{uuid_mod.uuid4().hex[:8]}P{os.getpid()}M{socket.gethostname()}:2,"
            cur_path = cur_dir / unique_name
            cur_path.write_bytes(mime_bytes)
        except Exception as exc:
            log.error("Failed to add message %s to Maildir: %s", uuid, exc)

        # Write CSV row
        if msg is not None:
            self._csv_writer.writerow({
                "uuid": uuid,
                "source": source,
                "message_id": msg_id,
                "from": str(msg.get("From", "")),
                "to": str(msg.get("To", "")),
                "subject": str(msg.get("Subject", "")),
                "date": str(msg.get("Date", "")),
                "source_file": source,
            })
        else:
            headers = {}
            for line in mime_bytes.split(b"\r\n")[:50]:
                if b":" in line:
                    key, _, val = line.partition(b":")
                    headers[key.decode("ascii", errors="replace").lower()] = val.decode("utf-8", errors="replace").strip()
            self._csv_writer.writerow({
                "uuid": uuid,
                "source": source,
                "message_id": msg_id,
                "from": headers.get("from", ""),
                "to": headers.get("to", ""),
                "subject": headers.get("subject", ""),
                "date": headers.get("date", ""),
                "source_file": source,
            })
        return True

    def write_attachment(self, uuid: str, filename: str, data: bytes) -> str:
        """Write decoded attachment bytes. Returns sanitized filename."""
        att_dir = self.out / "attachments" / uuid
        att_dir.mkdir(parents=True, exist_ok=True)

        existing = {f.name for f in att_dir.iterdir()} if att_dir.exists() else set()
        safe_name = _sanitize_filename(filename, existing=existing)

        (att_dir / safe_name).write_bytes(data)
        return safe_name

    def flush(self) -> None:
        self._csv_file.flush()
        self._csv_file.close()

