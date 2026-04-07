"""Tests for message/* attachment handling (RFC 822 forwarded emails)."""
import pytest
from parsers.attachment import parse_attachment


class TestMessageAttachments:
    """Verify parse_attachment handles message/rfc822 and related types."""

    def test_message_rfc822_no_cte_returns_raw_body(self):
        """message/rfc822 without CTE should return raw body, not try base64."""
        data = (
            b"Content-Type: message/rfc822\r\n"
            b"\r\n"
            b"From: sender@example.com\r\n"
            b"Subject: Test Forwarded Email\r\n"
            b"To: recipient@example.com\r\n"
            b"\r\n"
            b"This is the forwarded email body."
        )
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1
        filename, content_type, decoded = result[0]
        assert content_type == "message/rfc822"
        assert "forwarded_test-forwarded-email" in filename
        assert decoded == (
            b"From: sender@example.com\r\n"
            b"Subject: Test Forwarded Email\r\n"
            b"To: recipient@example.com\r\n"
            b"\r\n"
            b"This is the forwarded email body."
        )

    def test_message_rfc822_no_subject_uses_fallback_filename(self):
        """message/rfc822 without Subject header should use fallback filename."""
        data = (
            b"Content-Type: message/rfc822\r\n"
            b"\r\n"
            b"From: sender@example.com\r\n"
            b"To: recipient@example.com\r\n"
            b"\r\n"
            b"Body without subject."
        )
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, list)
        filename, content_type, decoded = result[0]
        assert filename == "forwarded_message.eml"

    def test_message_delivery_status_no_cte_returns_raw_body(self):
        """message/delivery-status without CTE should return raw body."""
        data = (
            b"Content-Type: message/delivery-status\r\n"
            b"\r\n"
            b"Final-Recipient: rfc822; user@example.com\r\n"
            b"Status: 5.0.0\r\n"
            b"\r\n"
            b"Delivery failed."
        )
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1
        filename, content_type, decoded = result[0]
        assert content_type == "message/delivery-status"
        assert decoded == (
            b"Final-Recipient: rfc822; user@example.com\r\n"
            b"Status: 5.0.0\r\n"
            b"\r\n"
            b"Delivery failed."
        )

    def test_message_rfc822_with_cte_still_decodes_base64(self):
        """message/rfc822 WITH CTE=base64 should still decode base64."""
        data = (
            b"Content-Type: message/rfc822\r\n"
            b"Content-Transfer-Encoding: base64\r\n"
            b"\r\n"
            b"RnJvbTogc2VuZGVyQGV4YW1wbGUuY29tClN1YmplY3Q6IFRlc3QKVG86IHJlY2lwaWVudEBleGFtcGxlLmNvbQoKVGhpcyBpcyB0aGUgYm9keS4="
        )
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1
        filename, content_type, decoded = result[0]
        assert content_type == "message/rfc822"
        assert b"From: sender@example.com" in decoded

    def test_message_rfc822_truncated_body_returns_error(self):
        """message/rfc822 with truly invalid/truncated body returns error tuple."""
        data = (
            b"Content-Type: message/rfc822\r\n"
            b"\r\n"
            b"Subject:"  # Truncated mid-line
        )
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1

    def test_base64_failure_still_returns_error_tuple(self):
        """Non-message/* with invalid base64 should still return error tuple."""
        data = (
            b"Content-Type: application/pdf\r\n"
            b"Content-Transfer-Encoding: base64\r\n"
            b"\r\n"
            b"!!!not-valid-base64!!!\r\n"
        )
        result = parse_attachment(data)
        assert result is not None
        assert isinstance(result, tuple)
        assert result[0] is None
        assert "base64" in result[1]


class TestMakeRfc822Filename:
    """Test the subject extraction logic for forwarded email filenames."""

    def test_extracts_subject_from_body(self):
        from parsers.attachment import _make_rfc822_filename

        body = (
            b"From: sender@example.com\r\n"
            b"Subject: Important Meeting Notes\r\n"
            b"To: team@example.com\r\n"
        )
        filename = _make_rfc822_filename(body, "attachment")
        assert filename == "forwarded_important-meeting-notes.eml"

    def test_long_subject_truncated(self):
        from parsers.attachment import _make_rfc822_filename

        body = (
            b"Subject: " + b"A" * 100 + b"\r\n"
        )
        filename = _make_rfc822_filename(body, "attachment")
        assert len(filename) <= 70
        assert filename.startswith("forwarded_")
        assert filename.endswith(".eml")

    def test_no_subject_uses_fallback(self):
        from parsers.attachment import _make_rfc822_filename

        body = b"From: sender@example.com\r\nTo: recipient@example.com\r\n"
        filename = _make_rfc822_filename(body, "attachment")
        assert filename == "forwarded_message.eml"

    def test_non_ascii_subject_handled(self):
        from parsers.attachment import _make_rfc822_filename

        body = "Subject: Meeting at 2pm 📅\r\n".encode("utf-8")
        filename = _make_rfc822_filename(body, "attachment")
        assert "forwarded_" in filename
        assert filename.endswith(".eml")