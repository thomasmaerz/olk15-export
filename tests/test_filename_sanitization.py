"""Tests for RFC 2047 filename decoding and filesystem sanitization."""
import pytest
from parsers.attachment import _decode_filename
from writer import _sanitize_filename


class TestDecodeFilename:
    """Verify RFC 2047 and RFC 5987 filename decoding."""

    def test_decodes_rfc2047_base64(self):
        """Decode =?UTF-8?B?...?= encoded-words."""
        raw = ' =?UTF-8?B?MV9sZWFzZV/np5/os4PlkIjntIQ=?=.1.pdf'
        result = _decode_filename(raw)
        assert "1_lease_" in result
        assert result.endswith(".1.pdf")

    def test_decodes_rfc2047_quoted_printable(self):
        """Decode =?UTF-8?Q?...?= encoded-words."""
        raw = '=?UTF-8?Q?hello_world.txt?='
        result = _decode_filename(raw)
        assert result == "hello world.txt"

    def test_decodes_rfc5987_percent_encoded(self):
        """Decode filename*=UTF-8''percent-encoded format."""
        raw = "UTF-8''1_lease_%E7%A7%9F%E8%B3%83%E5%90%88%E7%B4%84.1.pdf"
        result = _decode_filename(raw)
        assert result.endswith(".1.pdf")

    def test_strips_leading_whitespace(self):
        """Leading space in filename should be stripped."""
        raw = ' leading_space.txt'
        result = _decode_filename(raw)
        assert result == "leading_space.txt"

    def test_plain_filename_unchanged(self):
        """Plain ASCII filenames pass through unchanged."""
        raw = "document.pdf"
        result = _decode_filename(raw)
        assert result == "document.pdf"

    def test_strips_surrounding_quotes(self):
        """Quoted filenames have quotes removed."""
        raw = '"quoted_name.pdf"'
        result = _decode_filename(raw)
        assert result == "quoted_name.pdf"

    def test_preserves_spaces(self):
        """Spaces in decoded filenames should be preserved."""
        raw = "my document.pdf"
        result = _decode_filename(raw)
        assert result == "my document.pdf"

    def test_preserves_spaces_in_encoded(self):
        """Spaces in RFC 2047 encoded filenames should be preserved."""
        raw = '=?UTF-8?Q?my_document.pdf?='
        result = _decode_filename(raw)
        assert " " in result or result == "my document.pdf"


class TestSanitizeFilename:
    """Verify filesystem-safe filename sanitization."""

    def test_strips_leading_trailing_whitespace(self):
        result = _sanitize_filename("  file.txt  ")
        assert result == "file.txt"

    def test_replaces_path_separators(self):
        result = _sanitize_filename("path/file.txt")
        assert "/" not in result
        result = _sanitize_filename("path\\file.txt")
        assert "\\" not in result

    def test_replaces_invalid_chars(self):
        for ch in [":", "*", "?", '"', "<", ">", "|"]:
            result = _sanitize_filename(f"file{ch}name.txt")
            assert ch not in result

    def test_truncates_long_filenames(self):
        long_name = "a" * 300 + ".pdf"
        result = _sanitize_filename(long_name)
        assert len(result) <= 200
        assert result.endswith(".pdf")

    def test_collision_suffix(self):
        result = _sanitize_filename("file.txt", existing={"file.txt"})
        assert result != "file.txt"
        assert result.startswith("file")
        assert result.endswith(".txt")