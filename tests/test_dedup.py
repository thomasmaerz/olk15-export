"""Tests for Message-ID deduplication in EmlWriter."""
import pathlib
import pytest
from writer import EmlWriter


def make_mime(message_id: str, subject: str = "Test") -> bytes:
    """Build minimal valid MIME bytes with the given Message-ID."""
    lines = [
        f"Message-ID: {message_id}",
        f"Subject: {subject}",
        "From: test@example.com",
        "To: recipient@example.com",
        "Date: Mon, 01 Jan 2024 00:00:00 +0000",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "Hello world",
        "",
    ]
    return "\r\n".join(lines).encode("utf-8")


class TestMessageIdDedup:
    """Verify that Message-ID dedup works across different header formats."""

    def test_duplicate_with_identical_ids(self, tmp_path: pathlib.Path):
        """Two messages with the exact same Message-ID should dedup."""
        writer = EmlWriter(tmp_path)
        mime = make_mime("<abc123@example.com>")

        result1 = writer.write_eml("uuid1", mime, source="sources")
        result2 = writer.write_eml("uuid2", mime, source="messages")

        assert result1 is True
        assert result2 is False  # duplicate should be skipped

    def test_duplicate_with_angle_brackets_vs_without(self, tmp_path: pathlib.Path):
        """Message-ID with angle brackets should match one without."""
        writer = EmlWriter(tmp_path)
        # Source files produce IDs with angle brackets (RFC 2822 format)
        mime_source = make_mime("<BYAPR15MB1234@namprd15.prod.outlook.com>")
        # Message files produce IDs without angle brackets (from SQLite DB)
        mime_message = make_mime("BYAPR15MB1234@namprd15.prod.outlook.com")

        result1 = writer.write_eml("uuid1", mime_source, source="sources")
        result2 = writer.write_eml("uuid2", mime_message, source="messages")

        assert result1 is True
        assert result2 is False  # should be deduped

    def test_duplicate_without_angle_brackets_vs_with(self, tmp_path: pathlib.Path):
        """Order should not matter — without brackets first, then with."""
        writer = EmlWriter(tmp_path)
        mime_message = make_mime("BYAPR15MB1234@namprd15.prod.outlook.com")
        mime_source = make_mime("<BYAPR15MB1234@namprd15.prod.outlook.com>")

        result1 = writer.write_eml("uuid1", mime_message, source="messages")
        result2 = writer.write_eml("uuid2", mime_source, source="sources")

        assert result1 is True
        assert result2 is False

    def test_different_ids_not_deduped(self, tmp_path: pathlib.Path):
        """Two different Message-IDs should both be written."""
        writer = EmlWriter(tmp_path)
        mime1 = make_mime("<abc123@example.com>")
        mime2 = make_mime("<def456@example.com>")

        result1 = writer.write_eml("uuid1", mime1, source="sources")
        result2 = writer.write_eml("uuid2", mime2, source="sources")

        assert result1 is True
        assert result2 is True

    def test_missing_message_id_never_deduped(self, tmp_path: pathlib.Path):
        """Messages without Message-ID should never be deduped."""
        writer = EmlWriter(tmp_path)
        # MIME without Message-ID header
        mime_no_id = (
            b"Subject: No ID\r\n"
            b"From: test@example.com\r\n"
            b"To: recipient@example.com\r\n"
            b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Hello"
        )

        result1 = writer.write_eml("uuid1", mime_no_id, source="sources")
        result2 = writer.write_eml("uuid2", mime_no_id, source="messages")

        # Both should pass through — no Message-ID means no dedup
        assert result1 is True
        assert result2 is True

    def test_whitespace_and_brackets_combined(self, tmp_path: pathlib.Path):
        """Message-ID with whitespace AND angle brackets should normalize correctly."""
        writer = EmlWriter(tmp_path)
        mime1 = make_mime("  <BYAPR15MB1234@namprd15.prod.outlook.com>  ")
        mime2 = make_mime("BYAPR15MB1234@namprd15.prod.outlook.com")

        result1 = writer.write_eml("uuid1", mime1, source="sources")
        result2 = writer.write_eml("uuid2", mime2, source="messages")

        assert result1 is True
        assert result2 is False
