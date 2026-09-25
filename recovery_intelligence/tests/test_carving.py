import hashlib
from pathlib import Path
import pytest

from recovery.evidence_hash import calculate_sha256, validate_evidence_file, create_evidence_record
from recovery.carving import carve_fragments
from pipeline.orchestrator import run_stage_1

def _build_synthetic_evidence_bytes() -> bytes:
    """Generate deterministic synthetic disk image containing multiple signature formats and noise."""
    buffer = bytearray()
    
    # 1. Leading noise (128 bytes)
    buffer.extend(b"\x00\x11\x22\x33" * 32)
    
    # 2. JPEG candidate (header + payload + footer)
    jpeg_header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00\x48\x00\x48\x00\x00"
    jpeg_payload = b"\xfe\xdc\xba\x98" * 16
    jpeg_footer = b"\xff\xd9"
    buffer.extend(jpeg_header + jpeg_payload + jpeg_footer)
    
    # 3. Intermediary noise (64 bytes)
    buffer.extend(b"\x55\xaa" * 32)
    
    # 4. PDF candidate (header + payload + footer)
    pdf_header = b"%PDF-1.4\n"
    pdf_payload = b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    pdf_footer = b"%%EOF\n"
    buffer.extend(pdf_header + pdf_payload + pdf_footer)
    
    # 5. Intermediary noise (64 bytes)
    buffer.extend(b"\xff\x00\xff\x00" * 16)
    
    # 6. ZIP candidate (header + payload + footer)
    zip_header = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"
    zip_payload = b"sample_file.txtDATA_STREAM"
    zip_footer = b"PK\x05\x06" + (b"\x00" * 18)
    buffer.extend(zip_header + zip_payload + zip_footer)
    
    # 7. Intermediary noise (64 bytes)
    buffer.extend(b"\x99\x88\x77\x66" * 16)
    
    # 8. SQLite candidate (header with page size 4096 and page count 1)
    sqlite_header = bytearray(b"SQLite format 3\x00")
    sqlite_header.extend(b"\x10\x00")  # page size = 4096
    sqlite_header.extend(b"\x01\x01\x00\x40\x20\x20\x00\x00\x00\x00")
    sqlite_header.extend(b"\x00\x00\x00\x01")  # database size in pages = 1
    sqlite_header.extend(b"\x00" * 68)  # remainder of 100-byte SQLite header
    buffer.extend(sqlite_header)
    
    # 9. Trailing noise
    buffer.extend(b"\xee\xdd" * 32)
    
    return bytes(buffer)

@pytest.fixture
def synthetic_evidence(tmp_path: Path) -> Path:
    evidence_file = tmp_path / "test_evidence.dd"
    evidence_file.write_bytes(_build_synthetic_evidence_bytes())
    return evidence_file

def test_sha256_deterministic_and_matches_hashlib(synthetic_evidence: Path):
    """Test SHA-256 calculation matches hashlib directly and is deterministic across runs."""
    expected_hash = hashlib.sha256(synthetic_evidence.read_bytes()).hexdigest().lower()
    
    hash1 = calculate_sha256(synthetic_evidence)
    hash2 = calculate_sha256(synthetic_evidence)
    
    assert hash1 == expected_hash
    assert hash2 == expected_hash
    assert hash1 == hash2

def test_missing_evidence_file_raises_error(tmp_path: Path):
    """Test that missing evidence file raises FileNotFoundError."""
    non_existent = tmp_path / "non_existent.dd"
    with pytest.raises(FileNotFoundError):
        calculate_sha256(non_existent)
    with pytest.raises(FileNotFoundError):
        carve_fragments(non_existent)

def test_empty_evidence_file_rejected(tmp_path: Path):
    """Test that empty evidence file (0 bytes) is rejected with ValueError."""
    empty_file = tmp_path / "empty.dd"
    empty_file.write_bytes(b"")
    
    with pytest.raises(ValueError, match="empty"):
        calculate_sha256(empty_file)
    with pytest.raises(ValueError, match="empty"):
        carve_fragments(empty_file)

def test_directory_path_rejected(tmp_path: Path):
    """Test that passing a directory instead of a regular file raises ValueError."""
    with pytest.raises(ValueError, match="regular file"):
        calculate_sha256(tmp_path)

def test_all_supported_signatures_detected(synthetic_evidence: Path):
    """Test that JPEG, PDF, ZIP, and SQLite candidates are all detected."""
    fragments = carve_fragments(synthetic_evidence)
    detected_types = {f.type_hint for f in fragments}
    
    assert "jpeg" in detected_types
    assert "pdf" in detected_types
    assert "zip" in detected_types
    assert "sqlite" in detected_types

def test_fragment_attributes_and_types(synthetic_evidence: Path):
    """Verify fragment offsets, lengths, deterministic IDs, flags, and source."""
    fragments = carve_fragments(synthetic_evidence)
    assert len(fragments) >= 4
    
    for idx, f in enumerate(fragments):
        assert isinstance(f.offset, int)
        assert f.offset >= 0
        assert isinstance(f.length, int)
        assert f.length > 0
        assert f.id == f"F{idx + 1:04d}"
        assert f.pipeline_tag == "carved"
        assert f.source == str(synthetic_evidence.resolve())
        assert f.entropy == 0.0  # Placeholder for stage 1
        assert "signature" in f.metadata
        assert "end_offset" in f.metadata
        assert f.metadata["end_offset"] == f.offset + f.length

def test_header_and_footer_flags(synthetic_evidence: Path):
    """Verify header and footer flags for formats with and without footers."""
    fragments = carve_fragments(synthetic_evidence)
    frag_by_type = {f.type_hint: f for f in fragments}
    
    # Formats with detected footers
    assert frag_by_type["jpeg"].header_flag is True
    assert frag_by_type["jpeg"].footer_flag is True
    
    assert frag_by_type["pdf"].header_flag is True
    assert frag_by_type["pdf"].footer_flag is True
    
    assert frag_by_type["zip"].header_flag is True
    assert frag_by_type["zip"].footer_flag is True
    
    # SQLite has no footer requirement
    assert frag_by_type["sqlite"].header_flag is True
    assert frag_by_type["sqlite"].footer_flag is False

def test_no_exact_duplicate_fragments(tmp_path: Path):
    """Verify duplicate signatures at different offsets are kept, but exact duplicates avoided."""
    buffer = bytearray()
    sig = b"\xff\xd8\xff\x00\x01\x02\xff\xd9"
    buffer.extend(sig)
    buffer.extend(b"\x00" * 32)
    buffer.extend(sig)  # Identical content at different offset
    
    evidence_file = tmp_path / "duplicates.dd"
    evidence_file.write_bytes(bytes(buffer))
    
    fragments = carve_fragments(evidence_file)
    assert len(fragments) == 2
    assert fragments[0].offset != fragments[1].offset
    assert fragments[0].id == "F0001"
    assert fragments[1].id == "F0002"

def test_evidence_file_never_modified(synthetic_evidence: Path):
    """Verify original evidence file is opened read-only and never mutated."""
    before_bytes = synthetic_evidence.read_bytes()
    before_mtime = synthetic_evidence.stat().st_mtime_ns
    
    _ = calculate_sha256(synthetic_evidence)
    _ = carve_fragments(synthetic_evidence)
    
    after_bytes = synthetic_evidence.read_bytes()
    after_mtime = synthetic_evidence.stat().st_mtime_ns
    
    assert before_bytes == after_bytes
    assert before_mtime == after_mtime

def test_pipeline_stage_1_execution(synthetic_evidence: Path):
    """Verify run_stage_1 returns valid Evidence model and Fragment list."""
    evidence, fragments = run_stage_1(str(synthetic_evidence))
    
    assert evidence.sha256 == calculate_sha256(synthetic_evidence)
    assert evidence.source_path == str(synthetic_evidence.resolve())
    assert len(fragments) >= 4
    assert evidence.evidence_id.startswith("EV-")
