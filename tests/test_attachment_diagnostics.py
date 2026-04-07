"""Tests for attachment parse failure diagnostics."""
import pytest
from parsers.attachment import parse_attachment


class TestAttachmentFailureReasons:
    """Verify that parse_attachment returns specific failure reasons."""

    def test_no_content_type_returns_reason(self):
        data = b"\xd0\x0d\x00\x00" + b"\x00" * 100
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, tuple)
        assert result[0] is None
        assert "Content-Type" in result[1]

    def test_no_header_body_separator_returns_reason(self):
        data = b"Content-Type: application/pdf\r\nNo separator here"
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, tuple)
        assert result[0] is None
        assert "separator" in result[1]

    def test_valid_mime_returns_results(self):
        data = (
            b"Content-Type: application/pdf; name=\"test.pdf\"\r\n"
            b"Content-Transfer-Encoding: base64\r\n"
            b"\r\n"
            b"SGVsbG8gV29ybGQ=\r\n"
        )
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) >= 1
        filename, content_type, decoded = result[0]
        assert filename == "test.pdf"
        assert content_type == "application/pdf"
        assert decoded == b"Hello World"

    def test_base64_decode_failure_returns_reason(self):
        data = (
            b"Content-Type: application/pdf; name=\"test.pdf\"\r\n"
            b"Content-Transfer-Encoding: base64\r\n"
            b"\r\n"
            b"!!!not-valid-base64!!!\r\n"
        )
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, tuple)
        assert result[0] is None
        assert "base64" in result[1]