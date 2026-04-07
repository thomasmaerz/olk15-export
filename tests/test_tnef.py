"""Tests for TNEF (winmail.dat) detection and unpacking."""
import pathlib
import pytest
from parsers.tnef import is_tnef, unpack_tnef
from parsers.attachment import parse_attachment

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


class TestIsTnef:
    """Verify TNEF detection logic."""

    def test_detects_by_filename(self):
        """winmail.dat should be detected regardless of content type."""
        assert is_tnef(filename="winmail.dat") is True
        assert is_tnef(filename="WINMAIL.DAT") is True
        assert is_tnef(filename="WinMail.Dat") is True
        assert is_tnef(filename="win.dat") is True

    def test_detects_by_content_type(self):
        """application/ms-tnef and application/vnd.ms-tnef should be detected."""
        assert is_tnef(content_type="application/ms-tnef") is True
        assert is_tnef(content_type="application/vnd.ms-tnef") is True
        assert is_tnef(content_type="APPLICATION/MS-TNEF") is True

    def test_detects_by_magic_bytes(self):
        """TNEF magic signature 0x223E9F78 should be detected."""
        tnef_data = b'\x78\x9f\x3e\x22' + b'\x00' * 20
        assert is_tnef(data=tnef_data) is True

    def test_non_tnef_returns_false(self):
        """Non-TNEF data should return False."""
        assert is_tnef(filename="report.pdf", content_type="application/pdf") is False
        assert is_tnef(filename="photo.jpg", content_type="image/jpeg") is False
        assert is_tnef(data=b'\x89PNG\r\n\x1a\n') is False

    def test_short_data_returns_false(self):
        """Data shorter than 4 bytes should not crash."""
        assert is_tnef(data=b'') is False
        assert is_tnef(data=b'\x78\x9f') is False


class TestUnpackTnef:
    """Verify TNEF unpacking logic."""

    def test_unpack_tnef_with_attachments(self):
        """Fixture 2 contains 1 file attachment."""
        fixture = FIXTURES_DIR / "winmail_tnef_2.olk15MsgAttachment"
        result = parse_attachment(fixture.read_bytes())
        assert result is not None
        assert len(result) == 1
        filename, content_type, data = result[0]
        assert len(data) > 0

    def test_unpack_tnef_meeting_request(self):
        """Fixture 1 is a meeting request with no file attachments."""
        fixture = FIXTURES_DIR / "winmail_tnef_1.olk15MsgAttachment"
        result = parse_attachment(fixture.read_bytes())
        assert result is not None
        assert len(result) == 1
        filename, content_type, data = result[0]
        assert filename == "winmail.dat"
        assert "ms-tnef" in content_type.lower()

    def test_unpack_tnef_invalid_data(self):
        """Invalid TNEF data should return empty list."""
        assert unpack_tnef(b'not a tnef file') == []
        assert unpack_tnef(b'') == []


class TestParseAttachmentWithTnef:
    """Verify parse_attachment handles TNEF correctly."""

    def test_regular_attachment_still_works(self):
        """Non-TNEF attachments should still return a single tuple."""
        fixture = FIXTURES_DIR / "winmail_tnef_2.olk15MsgAttachment"
        data = fixture.read_bytes()
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_tnef_returns_list(self):
        """TNEF attachments should return a list."""
        fixture = FIXTURES_DIR / "winmail_tnef_1.olk15MsgAttachment"
        data = fixture.read_bytes()
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, list)
