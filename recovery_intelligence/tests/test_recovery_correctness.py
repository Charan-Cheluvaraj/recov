import io
import os
import tempfile
import hashlib
import zipfile
import sqlite3
import pytest
from pathlib import Path
from PIL import Image

from config import settings
from models.fragment import Fragment
from models.cluster import FragmentCluster
from models.reconstructed_file import ReconstructedFile
from models.recoverability import RecoveryStatus
from recovery.carving import carve_fragments
from recovery.clustering import cluster_fragments
from recovery.fingerprinting import fit_and_fingerprint
from recovery.reconstruction import reconstruct_structured_file
from recovery.validation import (
    validate_reconstruction,
    validate_jpeg,
    validate_pdf,
    validate_docx,
    validate_zip,
    validate_sqlite,
    validate_text,
)
from recovery.recoverability import (
    calculate_recoverability_metrics,
    determine_recovery_status,
    assess_recoverability,
)
from recovery.text_reconstruction import compute_union_coverage
from pipeline.orchestrator import run_full_pipeline


# ============================================================
# 1. Multiple Adjacent JPEGs do NOT Merge
# ============================================================
def test_multiple_adjacent_jpegs_do_not_merge(tmp_path: Path):
    """
    Intentionally places two distinct JPEGs adjacent to each other in evidence.
    Verifies that format-aware carving and conservative clustering do NOT
    merge them into one bloated file.
    """
    # Create JPEG 1 (Red 16x16)
    img1 = Image.new("RGB", (16, 16), color="red")
    b1 = io.BytesIO()
    img1.save(b1, format="JPEG")
    jpeg1_bytes = b1.getvalue()

    # Create JPEG 2 (Blue 16x16)
    img2 = Image.new("RGB", (16, 16), color="blue")
    b2 = io.BytesIO()
    img2.save(b2, format="JPEG")
    jpeg2_bytes = b2.getvalue()

    ev_data = b"\x00" * 64 + jpeg1_bytes + b"\x00" * 32 + jpeg2_bytes + b"\x00" * 64
    ev_path = tmp_path / "two_adjacent_jpegs.raw"
    ev_path.write_bytes(ev_data)

    fragments = carve_fragments(ev_path)
    assert len(fragments) == 2, f"Expected 2 separate JPEG fragments, got {len(fragments)}"

    # Verify boundaries are distinct
    frag1 = fragments[0]
    frag2 = fragments[1]
    assert frag1.offset == 64
    assert frag1.length == len(jpeg1_bytes)
    assert frag2.offset == 64 + len(jpeg1_bytes) + 32
    assert frag2.length == len(jpeg2_bytes)

    # Verify clustering does NOT merge them
    fvs = fit_and_fingerprint(fragments)
    clusters, orphans = cluster_fragments(fvs, fragments=fragments)

    # In conservative clustering, two separate headers cannot be in the same cluster
    if clusters:
        for cl in clusters:
            assert len(cl.member_fragment_ids) <= 1 or set(cl.member_fragment_ids) != {frag1.id, frag2.id}


# ============================================================
# 2. Intact File Formats Validate 100%
# ============================================================
def test_intact_jpeg_validates_and_opens():
    img = Image.new("RGB", (32, 32), color="green")
    b = io.BytesIO()
    img.save(b, format="JPEG")
    jpeg_bytes = b.getvalue()

    valid, msg = validate_jpeg(jpeg_bytes)
    assert valid is True
    assert "Pillow parser" in msg


def test_intact_pdf_validates():
    minimal_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 10 10]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000103 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n164\n%%EOF"
    )
    valid, msg = validate_pdf(minimal_pdf)
    assert valid is True
    assert "page(s)" in msg


def test_intact_zip_validates():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test.txt", "Evidence payload")
    valid, msg = validate_zip(buf.getvalue())
    assert valid is True
    assert "zipfile parser" in msg


def test_intact_docx_validates():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        zf.writestr("word/document.xml", '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Forensics Test</w:t></w:r></w:p></w:body></w:document>')
    valid, msg = validate_docx(buf.getvalue())
    assert valid is True


def test_intact_sqlite_validates(tmp_path: Path):
    db_path = tmp_path / "valid.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, note TEXT);")
    cur.execute("INSERT INTO evidence VALUES (1, 'intact record');")
    conn.commit()
    conn.close()

    db_bytes = db_path.read_bytes()
    valid, msg = validate_sqlite(db_bytes)
    assert valid is True
    assert "integrity_check: ok" in msg


# ============================================================
# 3. Damaged JPEG Fails Validation and is NOT Falsely Recovered
# ============================================================
def test_damaged_jpeg_fails_validation_and_is_not_recovered():
    img = Image.new("RGB", (32, 32), color="purple")
    b = io.BytesIO()
    img.save(b, format="JPEG")
    intact = b.getvalue()

    # Corrupt by zeroing out the middle 100 bytes of entropy scan data
    damaged = intact[:150] + (b"\x00" * 100) + intact[250:]

    valid, msg = validate_jpeg(damaged)
    assert valid is False, "Corrupted JPEG must fail validation"

    with tempfile.NamedTemporaryFile(suffix=".dd", delete=False) as tf:
        tf.write(damaged)
        tf_path = tf.name
    try:
        frag = Fragment(id="f_damaged", offset=0, length=len(damaged), source=tf_path, type_hint="jpeg")
        recon_file = ReconstructedFile(
            id="recon_corrupt",
            cluster_id="c_corrupt",
            file_type="jpeg",
            fragment_ids=["f_damaged"],
            structural_validity=0.0,
            status="validation_failed",
            parser_message=msg,
        )
        assessed = assess_recoverability(recon_file, fragments=[frag])
        assert assessed.is_successfully_recovered is False
        assert assessed.recovery_state in ("STRUCTURALLY_INVALID", "PARTIALLY_RECONSTRUCTED")
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


# ============================================================
# 4. Unknown Format becomes RAW_BINARY_RECOVERY
# ============================================================
def test_unknown_format_becomes_raw_binary_salvage():
    raw_data = b"\x12\x34\x56\x78\x9a\xbc\xde\xf0" * 16
    valid, msg = validate_reconstruction("unknown", raw_data)
    assert valid is False

    st = determine_recovery_status(
        structural_validity=0.0,
        gap_count=0,
        recovered_bytes=len(raw_data),
        fragment_count=1,
        file_type="raw",
    )
    # Status for raw binary with valid bytes
    assert st == RecoveryStatus.RAW_BINARY_RECOVERY


# ============================================================
# 5. Union Byte Coverage & Gap Calculations
# ============================================================
def test_union_coverage_eliminates_duplicate_counting():
    f1 = Fragment(id="f1", offset=100, length=200)   # [100, 300)
    f2 = Fragment(id="f2", offset=200, length=200)   # [200, 400) - Overlaps with f1 by 100 bytes
    f3 = Fragment(id="f3", offset=500, length=100)   # [500, 600) - 100 byte gap from 400..500

    cov = compute_union_coverage([f1, f2, f3])
    assert cov["raw_fragment_bytes"] == 500
    assert cov["unique_recovered_bytes"] == 400  # [100..400) = 300 + [500..600) = 100
    assert cov["overlap_bytes"] == 100
    assert cov["gap_count"] == 1
    assert cov["total_gap_bytes"] == 100
    assert cov["observed_candidate_span"] == 500  # 400 + 100
    assert cov["source_ranges"] == [[100, 400], [500, 600]]


# ============================================================
# 6. Observational vs Logical Recovery Ratio Semantics
# ============================================================
def test_observed_vs_logical_recovery_semantics():
    rf = ReconstructedFile(
        id="recon_test",
        cluster_id="c_test",
        file_type="jpeg",
        unique_recovered_bytes=800,
        missing_or_unknown_bytes=200,
        observed_candidate_span=1000,
        observed_recovery_ratio=0.80,
    )
    # Without filesystem metadata
    assert rf.logical_recovery_ratio_available is False
    assert rf.logical_recovery_ratio is None
    assert rf.observed_recovery_ratio == 0.80

    # With filesystem metadata
    rf.known_original_size = 1600
    rf.logical_recovery_ratio = round(rf.unique_recovered_bytes / rf.known_original_size, 4)
    rf.logical_recovery_ratio_available = True

    assert rf.logical_recovery_ratio == 0.50
    assert rf.observed_recovery_ratio == 0.80


# ============================================================
# 7. Priority and Sensitivity Do NOT Override Validation
# ============================================================
def test_priority_and_sensitivity_never_override_validation():
    rf = ReconstructedFile(
        id="recon_high_pri",
        cluster_id="c_high_pri",
        file_type="jpeg",
        structural_validity=0.0,
        recovery_state="STRUCTURALLY_INVALID",
        composite_integrity_score=0.20,
        priority_score=0.95,  # High investigative triage priority
        sensitivity_level="CRITICAL",
    )
    # The validation gate MUST remain false despite high priority score and sensitivity
    assert rf.is_successfully_recovered is False
