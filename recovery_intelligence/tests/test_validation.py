import pytest
from recovery.validation import validate_jpeg, validate_pdf, validate_docx, validate_zip, validate_sqlite

def test_validation_interfaces():
    # Real parsers must honestly report validation failure on invalid dummy bytes
    valid, msg = validate_jpeg(b"dummy")
    assert valid is False
    assert "JPEG" in msg or "marker" in msg

    valid, msg = validate_pdf(b"dummy")
    assert valid is False
    assert "PDF" in msg

    valid, msg = validate_docx(b"dummy")
    assert valid is False
    assert "DOCX" in msg or "ZIP" in msg

    valid, msg = validate_zip(b"dummy")
    assert valid is False
    assert "ZIP" in msg

    valid, msg = validate_sqlite(b"dummy")
    assert valid is False
    assert "SQLite" in msg
