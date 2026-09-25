import inspect
import io
import tempfile
import zipfile
from pathlib import Path
from PIL import Image
import pytest

from models.reconstructed_file import ReconstructedFile
from models.sensitivity import SensitivityLevel, SensitivityAssessment
from intelligence.pii_detection import detect_pii
from intelligence.keyword_detection import detect_keywords
from intelligence.sensitivity import analyze_sensitivity, determine_sensitivity_level
from intelligence.priority import (
    calculate_priority_score,
    calculate_sensitivity_component,
    rank_reconstructed_candidates,
)
from pipeline.orchestrator import run_stage_8


# 1. Aadhaar-like pattern detection
def test_aadhaar_pattern_detection():
    sample_text = "The user provided identification proof: 4567 8901 2345 in verified records."
    matches = detect_pii(sample_text)
    categories = [m["category"] for m in matches]
    assert "aadhaar" in categories
    aadhaar_match = next(m for m in matches if m["category"] == "aadhaar")
    assert "XXXX-XXXX-2345" in aadhaar_match["match_snippet"]


# 2. PAN-like pattern detection
def test_pan_pattern_detection():
    sample_text = "Tax identification PAN is ABCDE1234F recorded on form 16."
    matches = detect_pii(sample_text)
    categories = [m["category"] for m in matches]
    assert "pan" in categories
    pan_match = next(m for m in matches if m["category"] == "pan")
    assert "A****234F" in pan_match["match_snippet"]


# 3. Email detection
def test_email_detection():
    sample_text = "Send incident logs to security-audit@enterprise-corp.org immediately."
    matches = detect_pii(sample_text)
    categories = [m["category"] for m in matches]
    assert "email" in categories
    email_match = next(m for m in matches if m["category"] == "email")
    assert "s***@enterprise-corp.org" in email_match["match_snippet"]


# 4. Phone detection
def test_phone_detection():
    sample_text = "Primary contact for subject is +91-9876543210 during investigation hours."
    matches = detect_pii(sample_text)
    categories = [m["category"] for m in matches]
    assert "phone" in categories


# 5. URL detection
def test_url_detection():
    sample_text = "Artifact reference discovered at https://evidence-vault.internal.net/case/8821 for triage."
    matches = detect_pii(sample_text)
    categories = [m["category"] for m in matches]
    assert "url" in categories


# 6. Credit card pattern detection
def test_credit_card_detection():
    sample_text = "Customer billing record: 4111-2222-3333-4444 approved transaction."
    matches = detect_pii(sample_text)
    categories = [m["category"] for m in matches]
    assert "credit_card" in categories
    card_match = next(m for m in matches if m["category"] == "credit_card")
    assert "****-****-****-4444" in card_match["match_snippet"]


# 7. Password / API Key detection
def test_credential_detection():
    sample_text = "api_key = 'abcdef1234567890abcdef1234567890' \n password: SecretPassword123!"
    matches = detect_pii(sample_text)
    categories = [m["category"] for m in matches]
    assert "credential" in categories


# 8. Sensitive keyword detection
def test_sensitive_keyword_detection():
    sample_text = "This document is strictly CONFIDENTIAL and RESTRICTED. Internal use only."
    matches = detect_keywords(sample_text)
    assert len(matches) >= 3
    pattern_names = [m["pattern_name"] for m in matches]
    assert "Confidentiality Indicator" in pattern_names
    assert "Restricted Access Marker" in pattern_names


# 9. No-match candidate classified as NONE
def test_no_match_candidate():
    sample_text = "The quick brown fox jumps over the lazy dog. General technical documentation."
    assessment = analyze_sensitivity(sample_text, candidate_id="cand_clean")
    assert assessment.sensitivity_level == SensitivityLevel.NONE
    assert assessment.match_count == 0
    assert len(assessment.detected_categories) == 0
    assert "Classified as NONE" in assessment.explanation


# 10. Multiple-category detection & determinism
def test_multiple_category_detection():
    sample_text = (
        "CONFIDENTIAL TAX FILING\n"
        "Name: John Doe\n"
        "PAN: ABCDE1234F\n"
        "Aadhaar: 4567 8901 2345\n"
        "Email: john.doe@taxdept.gov.in\n"
        "Phone: 9876543210\n"
    )
    assessment = analyze_sensitivity(sample_text, candidate_id="cand_multi")
    assert assessment.sensitivity_level == SensitivityLevel.HIGH
    assert "pan" in assessment.detected_categories
    assert "aadhaar" in assessment.detected_categories
    assert "email" in assessment.detected_categories
    assert "sensitive_keyword" in assessment.detected_categories


# 11. Sensitivity level determinism
def test_sensitivity_level_determinism():
    # Credentials -> HIGH
    assert determine_sensitivity_level(["credential"], [{"category": "credential"}]) == SensitivityLevel.HIGH

    # Credit card -> HIGH
    assert determine_sensitivity_level(["credit_card"], [{"category": "credit_card"}]) == SensitivityLevel.HIGH

    # Aadhaar + PAN -> HIGH
    assert determine_sensitivity_level(["aadhaar", "pan"], [{"category": "aadhaar"}, {"category": "pan"}]) == SensitivityLevel.HIGH

    # Single PAN -> MEDIUM
    assert determine_sensitivity_level(["pan"], [{"category": "pan"}]) == SensitivityLevel.MEDIUM

    # Single Email -> LOW
    assert determine_sensitivity_level(["email"], [{"category": "email"}]) == SensitivityLevel.LOW

    # Zero categories -> NONE
    assert determine_sensitivity_level([], []) == SensitivityLevel.NONE


# 12. Score boundedness [0.0, 1.0]
def test_priority_score_boundedness():
    # Maximum inputs
    p_max, _ = calculate_priority_score(
        composite_integrity=1.0,
        observed_recovery_ratio=1.0,
        structural_validity=1.0,
        recovered_bytes=100000,
        sensitivity_level=SensitivityLevel.HIGH,
        category_count=5,
        ambiguous=False,
        corruption_estimate=0.0,
    )
    assert 0.0 <= p_max <= 1.0

    # Minimum inputs with heavy penalties
    p_min, _ = calculate_priority_score(
        composite_integrity=0.0,
        observed_recovery_ratio=0.0,
        structural_validity=0.0,
        recovered_bytes=0,
        sensitivity_level=SensitivityLevel.NONE,
        category_count=0,
        ambiguous=True,
        corruption_estimate=1.0,
    )
    assert 0.0 <= p_min <= 1.0
    assert p_min == 0.0


# 13. Priority weight normalization
def test_priority_weight_normalization():
    # Arbitrary unnormalized weights should yield the exact same bounded priority
    unnorm_weights = {
        "integrity": 50.0,
        "recoverability": 40.0,
        "structural": 30.0,
        "sensitivity": 60.0,
        "size": 20.0,
    }
    norm_weights = {
        "integrity": 0.25,
        "recoverability": 0.20,
        "structural": 0.15,
        "sensitivity": 0.30,
        "size": 0.10,
    }

    score_unnorm, _ = calculate_priority_score(
        0.8, 0.7, 1.0, 4096, SensitivityLevel.MEDIUM, 2, weights=unnorm_weights
    )
    score_norm, _ = calculate_priority_score(
        0.8, 0.7, 1.0, 4096, SensitivityLevel.MEDIUM, 2, weights=norm_weights
    )
    assert abs(score_unnorm - score_norm) < 1e-4


# 14. Priority ordering & deterministic tie-breaking
def test_priority_ordering_and_tie_breaking():
    # Candidate A: High priority (high integrity, high sensitivity)
    cand_a = ReconstructedFile(
        id="cand_a",
        cluster_id="c1",
        composite_integrity_score=0.90,
        observed_recovery_ratio=0.95,
        recovered_bytes=8192,
        priority_score=0.88,
    )
    # Candidate B: Medium priority
    cand_b = ReconstructedFile(
        id="cand_b",
        cluster_id="c2",
        composite_integrity_score=0.70,
        observed_recovery_ratio=0.75,
        recovered_bytes=4096,
        priority_score=0.62,
    )
    # Candidate C1 & C2: Tied priority_score (0.75)
    # C1 has higher composite_integrity_score than C2
    cand_c1 = ReconstructedFile(
        id="cand_c1",
        cluster_id="c3",
        composite_integrity_score=0.85,
        observed_recovery_ratio=0.80,
        recovered_bytes=2048,
        priority_score=0.75,
    )
    cand_c2 = ReconstructedFile(
        id="cand_c2",
        cluster_id="c4",
        composite_integrity_score=0.80,
        observed_recovery_ratio=0.80,
        recovered_bytes=2048,
        priority_score=0.75,
    )

    ranked = rank_reconstructed_candidates([cand_b, cand_c2, cand_a, cand_c1])
    # Expected order: cand_a (0.88), cand_c1 (0.75, integ 0.85), cand_c2 (0.75, integ 0.80), cand_b (0.62)
    ranked_ids = [r.id for r in ranked]
    assert ranked_ids == ["cand_a", "cand_c1", "cand_c2", "cand_b"]


# 15. Ambiguity and corruption penalties
def test_ambiguity_and_corruption_penalties():
    score_clean, _ = calculate_priority_score(
        0.8, 0.8, 1.0, 4096, SensitivityLevel.LOW, 1, ambiguous=False, corruption_estimate=0.0
    )
    score_ambig, reason_ambig = calculate_priority_score(
        0.8, 0.8, 1.0, 4096, SensitivityLevel.LOW, 1, ambiguous=True, corruption_estimate=0.0
    )
    score_corrupt, reason_corrupt = calculate_priority_score(
        0.8, 0.8, 1.0, 4096, SensitivityLevel.LOW, 1, ambiguous=False, corruption_estimate=0.8
    )

    assert score_ambig < score_clean
    assert "Ambiguity penalty" in reason_ambig

    assert score_corrupt < score_clean
    assert "Corruption penalty" in reason_corrupt


# 16. End-to-end Stage 8 pipeline execution
def test_end_to_end_stage_8_pipeline(tmp_path: Path):
    """Verify run_stage_8 executes full Stages 1-8 pipeline and produces ranked candidates."""
    ev_path = tmp_path / "stage8_demo_evidence.raw"

    img = Image.new("RGB", (32, 32), color=(10, 80, 180))
    buf = io.BytesIO()
    img.save(
        buf,
        format="JPEG",
        quality=90,
        comment="CONFIDENTIAL Subject PAN: ABCDE1234F Email: suspect@darkmarket.org Token: bearer 1234567890abcdef1234567890",
    )
    intact_jpeg = buf.getvalue()

    split_point1 = 250
    removed_bytes_len = 100
    split_point2 = split_point1 + removed_bytes_len

    reg1 = intact_jpeg[:split_point1]
    reg2 = intact_jpeg[split_point2:]

    leading_noise = b"\x5a\xa5" * 64
    gap_bytes = b"\x00" * 128
    trailing_noise = b"\x3c\xc3" * 64

    evidence_bytes = leading_noise + reg1 + gap_bytes + reg2 + trailing_noise
    ev_path.write_bytes(evidence_bytes)

    evidence, fragments, features, graph, clusters, orphans, ranked_files = run_stage_8(str(ev_path))

    assert evidence is not None
    assert len(fragments) >= 2
    assert len(ranked_files) >= 1

    top_cand = ranked_files[0]
    assert top_cand.priority_score > 0.0
    assert len(top_cand.priority_reason) > 0
    assert top_cand.sensitivity_level in ("HIGH", "MEDIUM")
    assert len(top_cand.detected_categories) >= 1
    assert any(cat in top_cand.detected_categories for cat in ("pan", "email", "credential", "sensitive_keyword"))


# 17. Ground truth is strictly never accessed in Stage 8 code
def test_ground_truth_never_accessed_stage8():
    import intelligence.pii_detection as pmod
    import intelligence.keyword_detection as kmod
    import intelligence.sensitivity as smod
    import intelligence.priority as prmod

    for mod in (pmod, kmod, smod, prmod):
        source = inspect.getsource(mod)
        assert "ground_truth.json" not in source
