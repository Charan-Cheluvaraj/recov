import io
import os
import tempfile
import zipfile
import sqlite3
import pytest
from PIL import Image

try:
    import docx
except ImportError:
    docx = None

from recovery.validation import (
    validate_jpeg,
    validate_pdf,
    validate_docx,
    validate_zip,
    validate_sqlite,
    validate_text,
    validate_reconstruction,
)


@pytest.fixture
def valid_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (32, 32), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def valid_pdf_bytes() -> bytes:
    return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 10 10]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000052 00000 n 
0000000103 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
164
%%EOF"""


@pytest.fixture
def valid_docx_bytes() -> bytes:
    doc = docx.Document()
    doc.add_paragraph("Stage 5 Forensic Reconstruction Verification")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def valid_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("evidence_log.txt", "Forensic reconstruction test data")
        zf.writestr("subfolder/data.bin", b"\x00\x01\x02\x03\x04")
    return buf.getvalue()


@pytest.fixture
def valid_sqlite_bytes() -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        tpath = tf.name
    conn = sqlite3.connect(tpath)
    conn.execute("CREATE TABLE carved_records (id INT PRIMARY KEY, name TEXT);")
    conn.execute("INSERT INTO carved_records VALUES (1, 'reconstructed_row');")
    conn.commit()
    conn.close()
    with open(tpath, "rb") as f:
        data = f.read()
    os.remove(tpath)
    return data


def test_jpeg_validation_success(valid_jpeg_bytes):
    valid, msg = validate_jpeg(valid_jpeg_bytes)
    assert valid is True
    assert "JPEG" in msg
    assert "Pillow" in msg


def test_jpeg_validation_failure_on_corrupt():
    corrupted = b"\xff\xd8\xff\xe0" + b"\x00" * 40 + b"not a real jpeg"
    valid, msg = validate_jpeg(corrupted)
    assert valid is False
    assert "Pillow" in msg or "failed" in msg


def test_pdf_validation_success(valid_pdf_bytes):
    valid, msg = validate_pdf(valid_pdf_bytes)
    assert valid is True
    assert "PDF" in msg
    assert "page(s)" in msg


def test_pdf_validation_failure_on_corrupt():
    corrupted = b"%PDF-1.4\ncorrupted xref table garbage data 12345"
    valid, msg = validate_pdf(corrupted)
    assert valid is False
    assert "PDF" in msg


def test_docx_validation_success(valid_docx_bytes):
    valid, msg = validate_docx(valid_docx_bytes)
    assert valid is True
    assert "DOCX" in msg
    assert "paragraph" in msg


def test_docx_validation_failure_on_corrupt():
    # Corrupted ZIP header or incomplete DOCX
    corrupted = b"PK\x03\x04" + b"incomplete docx payload"
    valid, msg = validate_docx(corrupted)
    assert valid is False
    assert "DOCX" in msg or "ZIP" in msg


def test_zip_validation_success(valid_zip_bytes):
    valid, msg = validate_zip(valid_zip_bytes)
    assert valid is True
    assert "ZIP" in msg
    assert "member(s)" in msg


def test_zip_validation_failure_on_corrupt():
    corrupted = b"PK\x03\x04" + b"\xff" * 50
    valid, msg = validate_zip(corrupted)
    assert valid is False
    assert "ZIP" in msg


def test_sqlite_validation_success(valid_sqlite_bytes):
    valid, msg = validate_sqlite(valid_sqlite_bytes)
    assert valid is True
    assert "SQLite" in msg
    assert "integrity_check: ok" in msg


def test_sqlite_validation_failure_on_corrupt():
    # Corrupt database header + random bytes
    corrupted = b"SQLite format 3\x00" + b"\x00\x02" + b"\xff" * 100
    valid, msg = validate_sqlite(corrupted)
    assert valid is False
    assert "SQLite" in msg


def test_text_validation():
    valid_text = b"This is a valid reconstructed text fragment. Continuity is preserved."
    valid, msg = validate_text(valid_text)
    assert valid is True
    assert "Valid text" in msg

    # Binary non-printable data
    binary_data = b"\x00\x01\x02\x03\x04\xff\xfe\xca\xfe"
    valid, msg = validate_text(binary_data)
    assert valid is False


def test_validate_reconstruction_dispatcher(
    valid_jpeg_bytes, valid_pdf_bytes, valid_docx_bytes, valid_zip_bytes, valid_sqlite_bytes
):
    assert validate_reconstruction("jpeg", valid_jpeg_bytes)[0] is True
    assert validate_reconstruction("jpg", valid_jpeg_bytes)[0] is True
    assert validate_reconstruction("pdf", valid_pdf_bytes)[0] is True
    assert validate_reconstruction("docx", valid_docx_bytes)[0] is True
    assert validate_reconstruction("zip", valid_zip_bytes)[0] is True
    assert validate_reconstruction("sqlite", valid_sqlite_bytes)[0] is True
    assert validate_reconstruction("text", b"Hello forensic reconstruction")[0] is True

    # Empty candidate
    valid, msg = validate_reconstruction("jpeg", b"")
    assert valid is False
    assert "empty" in msg

    # Unsupported format
    valid, msg = validate_reconstruction("unknown_format_xyz", b"some bytes")
    assert valid is False
    assert "Unsupported" in msg
