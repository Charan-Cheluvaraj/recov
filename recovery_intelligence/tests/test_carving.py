"""
Stage 1 carving tests: evidence integrity, magic-byte detection, and format-aware fragment boundaries.

Tests updated to use Pillow-generated real JPEG/PNG/GIF bytes so that format-aware
boundary finders and min_size guards behave correctly with real file structures.
The synthetic PDF/ZIP/SQLite stubs remain unchanged since they don't need raster parsing.
"""
import hashlib
import io
import struct
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from recovery.evidence_hash import calculate_sha256, validate_evidence_file, create_evidence_record
from recovery.carving import carve_fragments
from pipeline.orchestrator import run_stage_1


# ─────────────────────────────────────────────────────────────
# Helpers for building synthetic evidence images
# ─────────────────────────────────────────────────────────────

def _make_jpeg_bytes(color: str = "red", size: tuple = (16, 16)) -> bytes:
    """Generate a real, Pillow-validated JPEG byte stream."""
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


def _make_pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 10 10]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000052 00000 n \n0000000103 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n164\n%%EOF"
    )


def _make_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test.txt", "synthetic payload")
    return buf.getvalue()


def _make_sqlite_bytes() -> bytes:
    hdr = bytearray(b"SQLite format 3\x00")
    hdr.extend(b"\x10\x00")          # page size = 4096
    hdr.extend(b"\x01\x01\x00\x40\x20\x20\x00\x00\x00\x00")
    hdr.extend(b"\x00\x00\x00\x01")  # page count = 1
    hdr.extend(b"\x00" * 68)         # rest of 100-byte header
    # Pad to exactly page_size bytes (4096) so PRAGMA calculations are valid
    hdr.extend(b"\x00" * (4096 - len(hdr)))
    return bytes(hdr)


def _build_synthetic_evidence_bytes() -> bytes:
    """
    Build a multi-format evidence image from real file bytes.
    Each section separated by 64 bytes of non-null noise to avoid null-gap detection.
    """
    noise_a = b"\x11\x22\x33\x44" * 16   # 64 bytes
    noise_b = b"\x55\xaa\x55\xaa" * 16   # 64 bytes
    noise_c = b"\xff\x01\xff\x01" * 16   # 64 bytes
    noise_d = b"\x99\x88\x77\x66" * 16   # 64 bytes

    jpeg = _make_jpeg_bytes()
    pdf = _make_pdf_bytes()
    zip_ = _make_zip_bytes()
    sqlite = _make_sqlite_bytes()

    return (
        noise_a
        + jpeg
        + noise_b
        + pdf
        + noise_c
        + zip_
        + noise_d
        + sqlite
        + noise_a  # trailing noise
    )


@pytest.fixture
def synthetic_evidence(tmp_path: Path) -> Path:
    evidence_file = tmp_path / "test_evidence.dd"
    evidence_file.write_bytes(_build_synthetic_evidence_bytes())
    return evidence_file


# ─────────────────────────────────────────────────────────────
# Tests: Evidence Integrity
# ─────────────────────────────────────────────────────────────

def test_sha256_deterministic_and_matches_hashlib(synthetic_evidence: Path):
    """SHA-256 calculation matches hashlib directly and is deterministic across runs."""
    expected_hash = hashlib.sha256(synthetic_evidence.read_bytes()).hexdigest().lower()

    hash1 = calculate_sha256(synthetic_evidence)
    hash2 = calculate_sha256(synthetic_evidence)

    assert hash1 == expected_hash
    assert hash2 == expected_hash
    assert hash1 == hash2


def test_missing_evidence_file_raises_error(tmp_path: Path):
    """Missing evidence file raises FileNotFoundError."""
    non_existent = tmp_path / "non_existent.dd"
    with pytest.raises(FileNotFoundError):
        calculate_sha256(non_existent)
    with pytest.raises(FileNotFoundError):
        carve_fragments(non_existent)


def test_empty_evidence_file_rejected(tmp_path: Path):
    """Empty evidence file (0 bytes) is rejected with ValueError."""
    empty_file = tmp_path / "empty.dd"
    empty_file.write_bytes(b"")

    with pytest.raises(ValueError, match="empty"):
        calculate_sha256(empty_file)
    with pytest.raises(ValueError, match="empty"):
        carve_fragments(empty_file)


def test_directory_path_rejected(tmp_path: Path):
    """Passing a directory instead of a regular file raises ValueError."""
    with pytest.raises(ValueError, match="regular file"):
        calculate_sha256(tmp_path)


# ─────────────────────────────────────────────────────────────
# Tests: Format Detection
# ─────────────────────────────────────────────────────────────

def test_all_supported_signatures_detected(synthetic_evidence: Path):
    """JPEG, PDF, ZIP, and SQLite candidates are all detected from multi-format image."""
    fragments = carve_fragments(synthetic_evidence)
    detected_types = {f.type_hint for f in fragments}

    assert "jpeg" in detected_types, f"JPEG not detected; types found: {detected_types}"
    assert "pdf" in detected_types, f"PDF not detected; types found: {detected_types}"
    assert "zip" in detected_types, f"ZIP not detected; types found: {detected_types}"
    assert "sqlite" in detected_types, f"SQLite not detected; types found: {detected_types}"


def test_fragment_attributes_and_types(synthetic_evidence: Path):
    """Fragment offsets, lengths, deterministic IDs, flags, and source are correct."""
    fragments = carve_fragments(synthetic_evidence)
    assert len(fragments) >= 4, f"Expected at least 4 fragments; got {len(fragments)}"

    for idx, f in enumerate(fragments):
        assert isinstance(f.offset, int)
        assert f.offset >= 0
        assert isinstance(f.length, int)
        assert f.length > 0
        assert f.id == f"F{idx + 1:04d}"
        assert f.pipeline_tag == "carved"
        assert f.source == str(synthetic_evidence.resolve())
        assert f.entropy == 0.0  # Placeholder for Stage 2
        assert "signature" in f.metadata
        assert "end_offset" in f.metadata
        assert f.metadata["end_offset"] == f.offset + f.length


def test_header_and_footer_flags(synthetic_evidence: Path):
    """Header and footer flags are set correctly per format."""
    fragments = carve_fragments(synthetic_evidence)
    frag_by_type = {f.type_hint: f for f in fragments}

    # Formats with detected footers
    assert frag_by_type["jpeg"].header_flag is True
    assert frag_by_type["jpeg"].footer_flag is True, \
        "Real JPEG with valid EOI must set footer_flag=True"

    assert frag_by_type["pdf"].header_flag is True
    assert frag_by_type["pdf"].footer_flag is True

    assert frag_by_type["zip"].header_flag is True
    assert frag_by_type["zip"].footer_flag is True

    # SQLite has no footer requirement
    assert frag_by_type["sqlite"].header_flag is True
    assert frag_by_type["sqlite"].footer_flag is False


def test_no_exact_duplicate_fragments(tmp_path: Path):
    """Two identical real JPEGs at different offsets produce 2 separate fragments."""
    jpeg = _make_jpeg_bytes(color="green")
    noise = b"\x55\xaa\x55\xaa" * 16  # 64 bytes non-null noise

    evidence_bytes = jpeg + noise + jpeg
    evidence_file = tmp_path / "duplicates.dd"
    evidence_file.write_bytes(evidence_bytes)

    fragments = carve_fragments(evidence_file)

    # Both JPEGs should be carved as separate fragments
    jpeg_frags = [f for f in fragments if f.type_hint == "jpeg"]
    assert len(jpeg_frags) == 2, (
        f"Expected 2 JPEG fragments from adjacent identical images; got {len(jpeg_frags)}. "
        f"All fragments: {[(f.offset, f.length, f.type_hint) for f in fragments]}"
    )
    assert jpeg_frags[0].offset != jpeg_frags[1].offset
    assert jpeg_frags[0].id == "F0001"
    assert jpeg_frags[1].id == "F0002"


def test_evidence_file_never_modified(synthetic_evidence: Path):
    """Original evidence file is opened read-only and never mutated."""
    before_bytes = synthetic_evidence.read_bytes()
    before_mtime = synthetic_evidence.stat().st_mtime_ns

    _ = calculate_sha256(synthetic_evidence)
    _ = carve_fragments(synthetic_evidence)

    after_bytes = synthetic_evidence.read_bytes()
    after_mtime = synthetic_evidence.stat().st_mtime_ns

    assert before_bytes == after_bytes
    assert before_mtime == after_mtime


def test_pipeline_stage_1_execution(synthetic_evidence: Path):
    """run_stage_1 returns valid Evidence model and Fragment list with >= 4 fragments."""
    evidence, fragments = run_stage_1(str(synthetic_evidence))

    assert evidence.sha256 == calculate_sha256(synthetic_evidence)
    assert evidence.source_path == str(synthetic_evidence.resolve())
    assert len(fragments) >= 4, f"Expected >= 4 fragments; got {len(fragments)}"
    assert evidence.evidence_id.startswith("EV-")
