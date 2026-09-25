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
    validate_tiff,
    validate_pcx,
    validate_wav,
    validate_png,
    validate_gif,
    validate_bmp,
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


# ============================================================
# 8. TIFF Validation: Real Pillow Round-Trip
# ============================================================
def test_intact_tiff_validates_pillow():
    img = Image.new("RGB", (16, 16), color=(80, 160, 240))
    b = io.BytesIO()
    img.save(b, format="TIFF")
    tiff_bytes = b.getvalue()

    valid, msg = validate_tiff(tiff_bytes)
    assert valid is True, f"Expected TIFF to validate; msg={msg}"
    assert "TIFF" in msg or "tiff" in msg.lower()


def test_corrupt_tiff_fails_validation():
    valid, msg = validate_tiff(b"II\x2a\x00" + b"\xff" * 50)
    assert valid is False, "Truncated/corrupt TIFF must fail validation"


def test_wrong_magic_tiff_fails():
    valid, msg = validate_tiff(b"\xff\xd8\xff" + b"\x00" * 50)
    assert valid is False
    assert "byte-order mark" in msg.lower() or "Missing TIFF" in msg


# ============================================================
# 9. PCX Validation: Pillow + Header Plausibility
# ============================================================
def test_intact_pcx_validates_pillow():
    img = Image.new("P", (16, 16))
    b = io.BytesIO()
    img.save(b, format="PCX")
    pcx_bytes = b.getvalue()

    valid, msg = validate_pcx(pcx_bytes)
    assert valid is True, f"Expected PCX to validate; msg={msg}"


def test_random_byte_not_pcx():
    """A random byte 0x0A that isn't a real PCX header must be rejected."""
    # Manufacturer byte matches but subsequent bytes don't match PCX spec
    fake_pcx = b"\x0a\xff\xff\xff" + b"\x00" * 200  # version=255 → invalid
    valid, msg = validate_pcx(fake_pcx)
    assert valid is False, "Random 0x0A should not validate as PCX"


# ============================================================
# 10. WAV Validation: wave Module Round-Trip
# ============================================================
def test_intact_wav_validates_wave_module():
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 1600)
    wav_bytes = buf.getvalue()

    valid, msg = validate_wav(wav_bytes)
    assert valid is True, f"Expected WAV to validate; msg={msg}"
    assert "16000 Hz" in msg or "wave parser" in msg


def test_riff_non_wave_fails_validation():
    """RIFF container that is not WAVE must fail WAV validation."""
    # RIFF + fake chunk type 'AVI '
    fake_riff = b"RIFF" + b"\x00\x00\x00\x10" + b"AVI " + b"\x00" * 40
    valid, msg = validate_wav(fake_riff)
    assert valid is False
    assert "WAVE" in msg or "RIFF" in msg


def test_truncated_wav_fails_validation():
    valid, msg = validate_wav(b"RIFF" + b"\x00" * 20)
    assert valid is False


# ============================================================
# 11. PNG Chunk Parsing
# ============================================================
def test_intact_png_validates_pillow():
    img = Image.new("RGB", (16, 16), color=(200, 100, 50))
    b = io.BytesIO()
    img.save(b, format="PNG")
    png_bytes = b.getvalue()

    valid, msg = validate_png(png_bytes)
    assert valid is True, f"Expected PNG to validate; msg={msg}"
    assert "PNG" in msg or "Pillow" in msg


def test_truncated_png_fails_validation():
    png_hdr = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    valid, msg = validate_png(png_hdr)
    assert valid is False


# ============================================================
# 12. BMP: Declared Size Must Be Plausible
# ============================================================
def test_intact_bmp_validates_pillow():
    img = Image.new("RGB", (16, 16), color="cyan")
    b = io.BytesIO()
    img.save(b, format="BMP")
    bmp_bytes = b.getvalue()

    valid, msg = validate_bmp(bmp_bytes)
    assert valid is True, f"Expected BMP to validate; msg={msg}"


def test_bm_with_impossible_size_does_not_carve(tmp_path: Path):
    """
    Bytes starting with 'BM' but with an absurd declared file size in
    bytes 2-5 must NOT produce a carving candidate.
    """
    # 'BM' header, declared size = 500 MB (way over max_scan_size=20MB)
    fake_bmp = b"BM" + (500 * 1024 * 1024).to_bytes(4, "little") + b"\x00" * 100
    ev_path = tmp_path / "fake_bmp.dd"
    ev_path.write_bytes(fake_bmp)

    fragments = carve_fragments(ev_path)
    bmp_frags = [f for f in fragments if f.type_hint == "bmp"]
    assert len(bmp_frags) == 0, "Implausible BMP declared size must be rejected"


# ============================================================
# 13. Carving: TIFF IFD Offset Validation
# ============================================================
def test_tiff_with_invalid_ifd_offset_does_not_carve(tmp_path: Path):
    """
    A TIFF magic header with an IFD offset pointing past EOF must
    NOT produce a carving candidate.
    """
    # II + 42 (little-endian) + IFD offset = 9999999 (way past file end)
    fake_tiff = b"II\x2a\x00" + (9999999).to_bytes(4, "little") + b"\x00" * 20
    ev_path = tmp_path / "fake_tiff.dd"
    ev_path.write_bytes(fake_tiff)

    fragments = carve_fragments(ev_path)
    tiff_frags = [f for f in fragments if f.type_hint == "tiff"]
    assert len(tiff_frags) == 0, "TIFF with invalid IFD offset must not produce a fragment"


# ============================================================
# 14. Carving: PCX False-Positive Rejection
# ============================================================
def test_pcx_random_0x0a_does_not_carve(tmp_path: Path):
    """
    Random data starting with 0x0A but with invalid PCX version/encoding
    must NOT produce a PCX carving candidate.
    """
    # 0x0A byte followed by junk PCX fields (version=99, encoding=7)
    fake_pcx = b"\x0a\x63\x07\x10" + b"\xff" * 200
    ev_path = tmp_path / "fake_pcx.dd"
    ev_path.write_bytes(fake_pcx)

    fragments = carve_fragments(ev_path)
    pcx_frags = [f for f in fragments if f.type_hint == "pcx"]
    assert len(pcx_frags) == 0, "Invalid PCX header bytes must be rejected by carving"


# ============================================================
# 15. Fingerprinting: FNV-1a Determinism
# ============================================================
def test_text_fingerprint_is_deterministic_across_calls():
    """
    Fingerprints must be identical when generated twice from the same input.
    Python's hash() is randomised per-process; FNV-1a32 is not.
    """
    import tempfile, os
    from recovery.fingerprinting import fit_and_fingerprint, read_fragment_bytes

    text = "Forensic evidence payload for fingerprint determinism test"
    text_bytes = text.encode("utf-8")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        f.write(text_bytes)
        tf = f.name

    try:
        frag = Fragment(
            id="F_det_test", offset=0, length=len(text_bytes),
            source=tf, type_hint="text",
            metadata={"characterization": "text"}
        )
        run1 = fit_and_fingerprint([frag])
        run2 = fit_and_fingerprint([frag])
        assert run1[0].vector == run2[0].vector, (
            "Text fingerprint vector must be identical across two calls "
            f"(FNV-1a)\n  run1={run1[0].vector[:8]}\n  run2={run2[0].vector[:8]}"
        )
    finally:
        os.unlink(tf)


# ============================================================
# 16. validate_reconstruction Dispatch for New Formats
# ============================================================
def test_validate_reconstruction_dispatch_tiff():
    img = Image.new("RGB", (8, 8), color=(10, 20, 30))
    b = io.BytesIO()
    img.save(b, format="TIFF")
    valid, msg = validate_reconstruction("tiff", b.getvalue())
    assert valid is True


def test_validate_reconstruction_dispatch_wav():
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * 800)
    valid, msg = validate_reconstruction("wav", buf.getvalue())
    assert valid is True
