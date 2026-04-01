from __future__ import annotations
import csv, email, email.policy, email.message, pathlib, logging, datetime, re, os
from email.parser import BytesParser

log = logging.getLogger(__name__)

CSV_FIELDS = ["uuid", "source", "message_id", "from", "to", "subject", "date", "source_file"]

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
        try:
            # Use compat32 for more lenient parsing of non-standard headers
            msg = BytesParser(policy=email.policy.compat32).parsebytes(mime_bytes)
        except Exception as exc:
            log.warning("Failed to parse MIME for %s: %s", uuid, exc)
            return False


        msg_id = (msg.get("Message-ID") or "").strip()
        if msg_id and msg_id in self._seen_ids:
            log.debug("Skipping duplicate Message-ID %s (uuid=%s)", msg_id, uuid)
            return False
        if msg_id:
            self._seen_ids.add(msg_id)

        # Write .eml
        eml_dir = self.out / source
        eml_dir.mkdir(parents=True, exist_ok=True)
        eml_path = eml_dir / f"{uuid}.eml"
        eml_path.write_bytes(mime_bytes)

        # Add to Maildir (write directly to cur/ with proper Maildir suffix)
        try:
            cur_dir = self.maildir_path / "cur"
            cur_dir.mkdir(parents=True, exist_ok=True)
            import uuid as uuid_mod
            unique_name = f"{datetime.datetime.now().timestamp()}.{uuid_mod.uuid4().hex[:8]}P{os.getpid()}MThomass-MacBook-Pro.local:2,"
            cur_path = cur_dir / unique_name
            cur_path.write_bytes(mime_bytes)
        except Exception as exc:
            log.error("Failed to add message %s to Maildir: %s", uuid, exc)

        # Write CSV row
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
        return True

    def write_attachment(self, uuid: str, filename: str, data: bytes) -> None:
        """Write decoded attachment bytes to output/attachments/<uuid>/<filename>."""
        att_dir = self.out / "attachments" / uuid
        att_dir.mkdir(parents=True, exist_ok=True)
        (att_dir / filename).write_bytes(data)

    def flush(self) -> None:
        self._csv_file.flush()
        self._csv_file.close()

