"""Tests for BytesParser fallback behavior in EmlWriter."""
import pathlib
import pytest
from writer import EmlWriter


def make_valid_mime(message_id: str = "<test@example.com>") -> bytes:
    return (
        f"Message-ID: {message_id}\r\n"
        f"Subject: Test\r\n"
        f"From: test@example.com\r\n"
        f"To: recipient@example.com\r\n"
        f"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"Hello world\r\n"
    ).encode("utf-8")


def make_malformed_mime() -> bytes:
    return (
        b"Message-ID: <malformed@example.com>\r\n"
        b"Subject: Test with bad header\r\n"
        b"From: test@example.com\r\n"
        b"X-Custom-Header: \x00\x01\x02binary garbage\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Hello world\r\n"
    )


class TestWriteEmlFallback:
    """Verify that messages with unparseable MIME are still written."""

    def test_valid_mime_writes_normally(self, tmp_path: pathlib.Path):
        writer = EmlWriter(tmp_path)
        mime = make_valid_mime()
        result = writer.write_eml("uuid1", mime, source="messages")
        assert result is True

    def test_malformed_mime_falls_back_to_raw_write(self, tmp_path: pathlib.Path):
        writer = EmlWriter(tmp_path)
        mime = make_malformed_mime()
        result = writer.write_eml("uuid_malformed", mime, source="messages")
        assert result is True

    def test_malformed_mime_appears_in_csv(self, tmp_path: pathlib.Path):
        writer = EmlWriter(tmp_path)
        mime = make_malformed_mime()
        writer.write_eml("uuid_malformed", mime, source="messages")
        writer.flush()

        csv_content = (tmp_path / "summary.csv").read_text()
        assert "uuid_malformed" in csv_content