import io
import os
import hashlib
import tempfile
import inspect
from pathlib import Path
from PIL import Image
import pytest

from models.fragment import Fragment
from models.cluster import FragmentCluster
from models.reconstructed_file import ReconstructedFile
from models.recoverability import RecoveryStatus, RecoverabilityAssessment
from recovery.recoverability import (
    calculate_recoverability_metrics,
    determine_recovery_status,
    generate_recovery_reason,
    write_recovered_artifact,
    assess_recoverability,
)
from recovery.disrupted_demo import generate_damaged_jpeg_evidence, generate_disrupted_text_evidence
from pipeline.orchestrator import run_stage_7


# 1. Recovered byte calculation
def test_recovered_byte_calculation():
    metrics = calculate_recoverability_metrics(
        recovered_bytes=1024,
        missing_or_unknown_bytes=256,
        gap_count=2,
        fragment_count=3,
    )
    assert metrics["recovered_bytes"] == 1024
    assert metrics["fragment_count"] == 3


# 2. Gap byte calculation & 3. Observed span calculation
def test_gap_byte_and_observed_span_calculation():
    rec_b = 4000
    gap_b = 1000
    metrics = calculate_recoverability_metrics(
        recovered_bytes=rec_b,
        missing_or_unknown_bytes=gap_b,
        gap_count=1,
        fragment_count=2,
    )
    assert metrics["missing_or_unknown_bytes"] == 1000
    assert metrics["gap_count"] == 1
    assert metrics["observed_candidate_span"] == rec_b + gap_b
    assert metrics["observed_candidate_span"] == 5000


# 4. Observed recovery ratio
def test_observed_recovery_ratio():
    # 4000 recovered out of 5000 observed span = 0.8000
    metrics = calculate_recoverability_metrics(4000, 1000, 1, 2)
    assert metrics["observed_recovery_ratio"] == 0.8

    # Edge cases: 0 span, 0 recovered
    zero_metrics = calculate_recoverability_metrics(0, 0, 0, 0)
    assert zero_metrics["observed_recovery_ratio"] == 0.0

    # 100% recovered (0 gaps)
    full_metrics = calculate_recoverability_metrics(2048, 0, 0, 1)
    assert full_metrics["observed_recovery_ratio"] == 1.0


# 5. Zero-gap candidate status (FULLY_RECONSTRUCTED vs STRUCTURALLY_INVALID)
def test_zero_gap_candidate_statuses():
    # Valid parser outcome + 0 gaps -> FULLY_RECONSTRUCTED
    st_valid = determine_recovery_status(
        structural_validity=1.0,
        gap_count=0,
        recovered_bytes=2048,
        fragment_count=1,
    )
    assert st_valid == RecoveryStatus.FULLY_RECONSTRUCTED

    # Failed parser outcome + 0 gaps -> STRUCTURALLY_INVALID
    st_invalid = determine_recovery_status(
        structural_validity=0.0,
        gap_count=0,
        recovered_bytes=2048,
        fragment_count=1,
    )
    assert st_invalid == RecoveryStatus.STRUCTURALLY_INVALID


# 6. Multi-gap candidate status
def test_multi_gap_candidate_statuses():
    # Parser valid + gaps -> STRUCTURALLY_VALID_PARTIAL
    st_valid_partial = determine_recovery_status(
        structural_validity=1.0,
        gap_count=2,
        recovered_bytes=3000,
        fragment_count=3,
    )
    assert st_valid_partial == RecoveryStatus.STRUCTURALLY_VALID_PARTIAL

    # Parser invalid + gaps -> PARTIALLY_RECONSTRUCTED
    st_partial = determine_recovery_status(
        structural_validity=0.0,
        gap_count=2,
        recovered_bytes=3000,
        fragment_count=3,
    )
    assert st_partial == RecoveryStatus.PARTIALLY_RECONSTRUCTED


# 7. Ambiguous candidate status
def test_ambiguous_candidate_status():
    st_ambig = determine_recovery_status(
        structural_validity=1.0,
        gap_count=1,
        recovered_bytes=1000,
        fragment_count=2,
        ambiguous=True,
    )
    assert st_ambig == RecoveryStatus.AMBIGUOUS

    st_ambig_str = determine_recovery_status(
        structural_validity=1.0,
        gap_count=0,
        recovered_bytes=1000,
        fragment_count=2,
        status="ambiguous",
    )
    assert st_ambig_str == RecoveryStatus.AMBIGUOUS


# 8. Unrecoverable candidate status
def test_unrecoverable_candidate_status():
    # 0 bytes recovered
    st_zero = determine_recovery_status(
        structural_validity=0.0,
        gap_count=0,
        recovered_bytes=0,
        fragment_count=0,
    )
    assert st_zero == RecoveryStatus.UNRECOVERABLE

    # cluster_only status
    st_cluster_only = determine_recovery_status(
        structural_validity=0.0,
        gap_count=0,
        recovered_bytes=100,
        fragment_count=1,
        status="cluster_only",
    )
    assert st_cluster_only == RecoveryStatus.UNRECOVERABLE


# 9. Artifact SHA-256 generation and disk writing
def test_artifact_sha256_generation(tmp_path: Path):
    test_bytes = b"RECOVERED_ARTIFACT_STAGE_7_DATA_STREAM"
    cand_id = "test_cand_001"
    
    path, sha = write_recovered_artifact(
        candidate_id=cand_id,
        file_type="jpeg",
        candidate_bytes=test_bytes,
        output_dir=tmp_path,
    )
    
    assert path.exists()
    assert path.name == f"recovered_{cand_id}.jpg"
    expected_sha = hashlib.sha256(test_bytes).hexdigest()
    assert sha == expected_sha
    assert path.read_bytes() == test_bytes


# 10. Fact-based recovery reason generation
def test_factual_recovery_reason():
    reason = generate_recovery_reason(
        fragment_count=3,
        recovered_bytes=12480,
        observed_candidate_span=15200,
        missing_bytes=2720,
        file_type="jpeg",
        structural_validity=1.0,
        recovery_status=RecoveryStatus.STRUCTURALLY_VALID_PARTIAL.value,
    )
    assert "3 associated fragments" in reason
    assert "12,480 bytes were recovered" in reason
    assert "15,200-byte observed span" in reason
    assert "2,720 bytes remain missing or unknown" in reason
    assert "JPEG structural validation succeeded" in reason
    assert "STRUCTURALLY_VALID_PARTIAL" in reason


# 11. assess_recoverability populates ReconstructedFile model completely
def test_assess_recoverability_populates_model(tmp_path: Path):
    ev_file = tmp_path / "evidence.raw"
    chunk1 = b"ABC" * 50
    chunk2 = b"XYZ" * 50
    gap = b"\x00" * 80
    ev_file.write_bytes(chunk1 + gap + chunk2)

    f1 = Fragment(
        id="F001",
        offset=0,
        length=len(chunk1),
        type_hint="text",
        source=str(ev_file),
    )
    f2 = Fragment(
        id="F002",
        offset=len(chunk1) + len(gap),
        length=len(chunk2),
        type_hint="text",
        source=str(ev_file),
    )

    recon = ReconstructedFile(
        id="recon_test",
        cluster_id="cluster_001",
        file_type="text",
        fragment_ids=["F001", "F002"],
        gap_information={"has_gaps": True, "gap_count": 1, "total_gap_bytes": len(gap), "gaps": []},
        structural_validity=1.0,
        status="reconstructed",
    )

    assessed = assess_recoverability(recon, fragments=[f1, f2], output_dir=tmp_path)

    assert assessed.recovered_bytes == len(chunk1) + len(chunk2)
    assert assessed.missing_or_unknown_bytes == len(gap)
    assert assessed.observed_candidate_span == len(chunk1) + len(chunk2) + len(gap)
    assert assessed.observed_recovery_ratio > 0.0
    assert assessed.gap_count == 1
    assert assessed.recovery_status == "STRUCTURALLY_VALID_PARTIAL"
    assert assessed.output_path != ""
    assert Path(assessed.output_path).exists()
    assert assessed.output_sha256 != ""


# 12. End-to-end damaged file recovery demo test
def test_end_to_end_damaged_file_recovery(tmp_path: Path):
    """
    Valid file -> split into surviving regions -> middle removed ->
    embedded in evidence -> run_stage_7() -> surviving fragments carved ->
    reconstructed -> validated -> recoverability quantified.
    """
    ev_path = tmp_path / "damaged_demo_evidence.raw"
    fixture_info = generate_damaged_jpeg_evidence(output_path=ev_path)

    evidence, fragments, features, graph, clusters, orphans, assessed_files = run_stage_7(
        fixture_info["evidence_path"]
    )

    # 1. Evidence was accepted and hashed
    assert evidence.sha256 == fixture_info["evidence_sha256"]

    # 2. Both surviving fragments were carved
    assert len(fragments) >= 2
    frag_types = {f.type_hint for f in fragments}
    assert "jpeg" in frag_types

    # 3. Candidates were assessed
    assert len(assessed_files) >= 1
    jpeg_candidates = [af for af in assessed_files if af.file_type == "jpeg"]
    assert len(jpeg_candidates) >= 1

    cand = jpeg_candidates[0]
    # 4. Verified exact calculated recovered bytes
    assert cand.recovered_bytes > 0
    assert cand.recovered_bytes == fixture_info["surviving_bytes_total"]

    # 5. Verified exact calculated gap bytes
    assert cand.missing_or_unknown_bytes == fixture_info["gap_len"]

    # 6. Verified observed candidate span
    assert cand.observed_candidate_span == cand.recovered_bytes + cand.missing_or_unknown_bytes

    # 7. Verified observed recovery ratio is bounded and correct
    expected_ratio = round(cand.recovered_bytes / cand.observed_candidate_span, 4)
    assert cand.observed_recovery_ratio == expected_ratio

    # 8. Real recovered file was written to disk and has valid SHA-256
    assert cand.output_path != ""
    assert Path(cand.output_path).exists()
    assert cand.output_sha256 != ""
    actual_file_sha = hashlib.sha256(Path(cand.output_path).read_bytes()).hexdigest()
    assert cand.output_sha256 == actual_file_sha

    # 9. Original evidence file was NEVER modified
    current_ev_sha = hashlib.sha256(ev_path.read_bytes()).hexdigest()
    assert current_ev_sha == fixture_info["evidence_sha256"]

    # 10. Status is STRUCTURALLY_VALID_PARTIAL because surviving portions form a valid JPEG container with gap
    assert cand.recovery_status == "STRUCTURALLY_VALID_PARTIAL"
    assert "STRUCTURALLY_VALID_PARTIAL" in cand.recovery_reason


def test_partially_reconstructed_status_on_corrupt_stream(tmp_path: Path):
    """Corrupted payload with internal gaps is classified as PARTIALLY_RECONSTRUCTED."""
    ev_file = tmp_path / "corrupt_gap_ev.raw"
    bad_header = b"\xff\xd8\xff\xe0" + b"\x00" * 20 + b"INVALID_CORRUPT_SEGMENT"
    gap = b"\x00" * 128
    bad_tail = b"MORE_CORRUPT_DATA" + b"\xff\xd9"
    ev_file.write_bytes(bad_header + gap + bad_tail)

    evidence, fragments, features, graph, clusters, orphans, assessed_files = run_stage_7(str(ev_file))
    assert len(assessed_files) >= 1
    cand = assessed_files[0]
    assert cand.gap_count >= 1
    assert cand.structural_validity == 0.0
    assert cand.recovery_status == "PARTIALLY_RECONSTRUCTED"
    assert "PARTIALLY_RECONSTRUCTED" in cand.recovery_reason




# 13. Ground truth is strictly never accessed in Stage 7 code
def test_ground_truth_never_accessed_stage7():
    import recovery.recoverability as rmod
    import recovery.carving as cmod
    import pipeline.orchestrator as omod

    for mod in (rmod, cmod, omod):
        source = inspect.getsource(mod)
        assert "ground_truth.json" not in source
