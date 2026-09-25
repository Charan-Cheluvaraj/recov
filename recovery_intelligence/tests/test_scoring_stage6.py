import io
import math
import hashlib
import pytest
from PIL import Image

from config.settings import settings
from models.cluster import FragmentCluster
from models.fragment import Fragment
from models.reconstructed_file import ReconstructedFile
from intelligence.scoring import (
    calculate_reconstruction_confidence,
    calculate_completeness,
    calculate_structural_validity,
    calculate_corruption_estimate,
    calculate_composite_integrity,
    score_reconstructed_file,
)
from pipeline.orchestrator import run_stage_6


# 1. Boundedness & Non-NaN/Inf
def test_all_signals_bounded_and_finite():
    test_cases = [
        # (conf_in, comp_in, val_in, corr_in)
        ({}, (0, 0, 0), True, (0, 0)),
        ({"cluster_confidence": 0.95, "member_count": 5}, (1000, 1000, 0), True, (0, 0)),
        ({"cluster_confidence": 0.0, "member_count": 0, "status": "cluster_only"}, (0, 0, 5), False, (5, 5)),
        ({"ambiguous": True}, (500, 200, 3), False, (2, 1)),
    ]

    for rels, comp_args, val_arg, corr_args in test_cases:
        conf = calculate_reconstruction_confidence(rels)
        comp = calculate_completeness(*comp_args)
        val = calculate_structural_validity(val_arg)
        corr = calculate_corruption_estimate(*corr_args)
        integ = calculate_composite_integrity(conf, comp, val, corr)

        for name, val_float in [("conf", conf), ("comp", comp), ("val", val), ("corr", corr), ("integ", integ)]:
            assert not math.isnan(val_float), f"{name} is NaN"
            assert not math.isinf(val_float), f"{name} is Inf"
            assert 0.0 <= val_float <= 1.0, f"{name} out of bounds [0, 1]: {val_float}"


# 2. Deterministic Scoring
def test_scoring_determinism():
    rf1 = ReconstructedFile(
        id="recon_1",
        cluster_id="c1",
        file_type="jpeg",
        fragment_ids=["f1", "f2"],
        gap_information={"has_gaps": True, "gap_count": 1, "total_gap_bytes": 64},
        structural_validity=1.0,
        status="reconstructed",
        parser_message="Valid JPEG image (32x32)",
    )
    cluster = FragmentCluster(cluster_id="c1", confidence=0.88, inferred_type="jpeg")
    fragments = [
        Fragment(id="f1", offset=0, length=256, type_hint="jpeg", header_flag=True),
        Fragment(id="f2", offset=320, length=256, type_hint="jpeg", footer_flag=True),
    ]

    scored_a = score_reconstructed_file(rf1.model_copy(), cluster, fragments)
    scored_b = score_reconstructed_file(rf1.model_copy(), cluster, fragments)

    assert scored_a.reconstruction_confidence == scored_b.reconstruction_confidence
    assert scored_a.completeness == scored_b.completeness
    assert scored_a.structural_validity == scored_b.structural_validity
    assert scored_a.corruption_estimate == scored_b.corruption_estimate
    assert scored_a.composite_integrity_score == scored_b.composite_integrity_score


# 3. Parser outcome influences structural validity
def test_parser_outcome_influences_structural_validity():
    val_success = calculate_structural_validity(parser_success=True)
    val_fail = calculate_structural_validity(parser_success=False, parser_message="Missing JPEG SOI marker")

    assert val_success == 1.0
    assert val_fail == 0.0
    assert val_success > val_fail


# 4. Gaps affect completeness
def test_gaps_affect_completeness():
    no_gaps = calculate_completeness(
        actual_size=1000,
        gap_information={"has_gaps": False, "gap_count": 0, "total_gap_bytes": 0},
    )
    with_gaps = calculate_completeness(
        actual_size=1000,
        gap_information={"has_gaps": True, "gap_count": 3, "total_gap_bytes": 500},
    )

    assert no_gaps > with_gaps
    assert 0.0 <= with_gaps <= 1.0


# 5. Gaps do NOT automatically equal corruption
def test_gaps_do_not_equal_corruption():
    # Candidate passed parser but had missing non-contiguous sections
    corr_no_gaps = calculate_corruption_estimate(parser_success=True, gap_count=0)
    corr_with_gaps = calculate_corruption_estimate(parser_success=True, gap_count=4)

    # Corruption should remain very low (0.0) when parser validates cleanly, regardless of gaps
    assert corr_with_gaps <= 0.10
    assert corr_with_gaps == corr_no_gaps


# 6. Ambiguity affects reconstruction confidence
def test_ambiguity_reduces_reconstruction_confidence():
    non_ambig = calculate_reconstruction_confidence(
        {"cluster_confidence": 0.85, "member_count": 3, "ambiguous": False, "status": "reconstructed"}
    )
    ambig = calculate_reconstruction_confidence(
        {"cluster_confidence": 0.85, "member_count": 3, "ambiguous": True, "status": "ambiguous"}
    )

    assert ambig < non_ambig
    assert ambig <= 0.45


# 7. Cluster confidence contributes to reconstruction confidence
def test_cluster_confidence_contribution():
    high_cl = calculate_reconstruction_confidence({"cluster_confidence": 1.0, "status": "reconstructed"})
    low_cl = calculate_reconstruction_confidence({"cluster_confidence": 0.1, "status": "reconstructed"})

    assert high_cl > low_cl


# 8. Composite uses configurable weights and handles weight normalization
def test_composite_configurable_weights_and_normalization():
    # If structural validity weight dominates
    w_validity_heavy = {"reconstruction_confidence": 0.0, "completeness": 0.0, "structural_validity": 1.0, "corruption": 0.0}
    comp_v = calculate_composite_integrity(0.5, 0.5, 1.0, 0.5, weights=w_validity_heavy)
    assert comp_v == 1.0

    # Unnormalized weights (e.g. sum to 100)
    w_unnorm = {"reconstruction_confidence": 25.0, "completeness": 25.0, "structural_validity": 35.0, "corruption": 15.0}
    w_norm = {"reconstruction_confidence": 0.25, "completeness": 0.25, "structural_validity": 0.35, "corruption": 0.15}

    score_unnorm = calculate_composite_integrity(0.8, 0.7, 0.9, 0.1, weights=w_unnorm)
    score_norm = calculate_composite_integrity(0.8, 0.7, 0.9, 0.1, weights=w_norm)

    assert score_unnorm == score_norm


# 9. Corruption inversion in composite score
def test_corruption_inversion_in_composite():
    # High corruption (1.0) should lower the composite score compared to low corruption (0.0)
    clean = calculate_composite_integrity(confidence=0.8, completeness=0.8, validity=1.0, corruption=0.0)
    corrupt = calculate_composite_integrity(confidence=0.8, completeness=0.8, validity=1.0, corruption=0.9)

    assert clean > corrupt


# 10. Special Case A: Fully validated candidate
def test_special_case_fully_validated():
    rf = ReconstructedFile(
        id="cand_clean",
        cluster_id="c_clean",
        file_type="jpeg",
        fragment_ids=["f1"],
        gap_information={"has_gaps": False, "gap_count": 0, "total_gap_bytes": 0},
        structural_validity=1.0,
        status="reconstructed",
        parser_message="Valid JPEG image (16x16)",
    )
    cluster = FragmentCluster(cluster_id="c_clean", confidence=0.92)
    frags = [Fragment(id="f1", offset=0, length=512, type_hint="jpeg", header_flag=True, footer_flag=True)]

    scored = score_reconstructed_file(rf, cluster, frags)

    assert scored.structural_validity == 1.0
    assert scored.completeness >= 0.95
    assert scored.corruption_estimate <= 0.05
    assert scored.composite_integrity_score >= 0.80


# 11. Special Case B: Candidate with gaps
def test_special_case_candidate_with_gaps():
    rf = ReconstructedFile(
        id="cand_gaps",
        cluster_id="c_gaps",
        file_type="pdf",
        fragment_ids=["f1", "f2"],
        gap_information={"has_gaps": True, "gap_count": 2, "total_gap_bytes": 1024},
        structural_validity=1.0,
        status="reconstructed",
        parser_message="Valid PDF document with 1 page(s)",
    )
    cluster = FragmentCluster(cluster_id="c_gaps", confidence=0.80)
    frags = [
        Fragment(id="f1", offset=0, length=512, type_hint="pdf"),
        Fragment(id="f2", offset=1536, length=512, type_hint="pdf"),
    ]

    scored = score_reconstructed_file(rf, cluster, frags)

    # Completeness is impacted by the gap
    assert scored.completeness < 0.80
    # But corruption is not falsely elevated because the PDF parsed successfully
    assert scored.corruption_estimate <= 0.10


# 12. Special Case C: Parser failure
def test_special_case_parser_failure():
    rf = ReconstructedFile(
        id="cand_fail",
        cluster_id="c_fail",
        file_type="zip",
        fragment_ids=["f1"],
        gap_information={"has_gaps": False, "gap_count": 0, "total_gap_bytes": 0},
        structural_validity=0.0,
        status="validation_failed",
        parser_message="ZIP CRC checksum failed",
    )
    cluster = FragmentCluster(cluster_id="c_fail", confidence=0.50)
    frags = [Fragment(id="f1", offset=0, length=256, type_hint="zip")]

    scored = score_reconstructed_file(rf, cluster, frags)

    assert scored.structural_validity == 0.0
    assert scored.corruption_estimate >= 0.75
    assert scored.composite_integrity_score < 0.50


# 13. Special Case D: Ambiguous candidate
def test_special_case_ambiguous_candidate():
    rf = ReconstructedFile(
        id="cand_ambig",
        cluster_id="c_ambig",
        file_type="text",
        fragment_ids=["t1", "t2"],
        gap_information={"has_gaps": False, "gap_count": 0, "total_gap_bytes": 0},
        structural_validity=1.0,
        status="ambiguous",
        ambiguous=True,
        parser_message="Ambiguous candidate: 2 orderings tied",
    )
    cluster = FragmentCluster(cluster_id="c_ambig", confidence=0.70)
    frags = [
        Fragment(id="t1", offset=0, length=64, type_hint="text"),
        Fragment(id="t2", offset=64, length=64, type_hint="text"),
    ]

    scored = score_reconstructed_file(rf, cluster, frags)

    assert scored.ambiguous is True
    assert scored.reconstruction_confidence <= 0.45


# 14. Special Case E: Cluster-only candidate
def test_special_case_cluster_only():
    rf = ReconstructedFile(
        id="cand_cl_only",
        cluster_id="c_none",
        file_type="unknown",
        fragment_ids=[],
        status="cluster_only",
        structural_validity=0.0,
        parser_message="No member fragments",
    )
    scored = score_reconstructed_file(rf, None, [])

    assert scored.structural_validity == 0.0
    assert scored.completeness == 0.0
    assert scored.corruption_estimate == 0.0
    assert scored.composite_integrity_score <= 0.20


# 15. run_stage_6 execution test
def test_run_stage_6_pipeline(tmp_path):
    # Create small evidence with 2 JPEG fragments that form a cluster
    img1 = Image.new("RGB", (16, 16), color="yellow")
    buf1 = io.BytesIO()
    img1.save(buf1, format="JPEG")
    jpeg1 = buf1.getvalue()

    img2 = Image.new("RGB", (16, 16), color="yellow")
    buf2 = io.BytesIO()
    img2.save(buf2, format="JPEG")
    jpeg2 = buf2.getvalue()

    ev_path = tmp_path / "stage6_ev.raw"
    with open(ev_path, "wb") as f:
        f.write(b"\x00" * 64 + jpeg1 + b"\x00" * 64 + jpeg2 + b"\x00" * 64)

    initial_sha = hashlib.sha256(open(ev_path, "rb").read()).hexdigest()

    evidence, fragments, features, graph, clusters, orphans, reconstructed = run_stage_6(str(ev_path))

    assert evidence is not None
    assert len(fragments) > 0
    assert len(features) == len(fragments)
    assert len(reconstructed) > 0

    for rf in reconstructed:
        assert isinstance(rf, ReconstructedFile)
        # All five Stage 6 signals are populated
        assert 0.0 <= rf.reconstruction_confidence <= 1.0
        assert 0.0 <= rf.completeness <= 1.0
        assert 0.0 <= rf.structural_validity <= 1.0
        assert 0.0 <= rf.corruption_estimate <= 1.0
        assert 0.0 <= rf.composite_integrity_score <= 1.0

    # Evidence remains strictly unchanged
    after_sha = hashlib.sha256(open(ev_path, "rb").read()).hexdigest()
    assert initial_sha == after_sha


# 16. Ground truth isolation
def test_ground_truth_never_accessed_stage6():
    import inspect
    import intelligence.scoring as sc_mod

    source = inspect.getsource(sc_mod)
    assert "ground_truth" not in source.lower()
