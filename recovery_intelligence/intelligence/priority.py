from typing import List, Dict, Any, Optional, Tuple
from config.settings import settings
from models.sensitivity import SensitivityLevel, SensitivityAssessment
from models.reconstructed_file import ReconstructedFile


def calculate_sensitivity_component(level: SensitivityLevel, category_count: int) -> float:
    """Map deterministic sensitivity level and category diversity to a bounded [0.0, 1.0] signal."""
    if level == SensitivityLevel.HIGH:
        base = 0.85
    elif level == SensitivityLevel.MEDIUM:
        base = 0.55
    elif level == SensitivityLevel.LOW:
        base = 0.25
    else:
        base = 0.0

    bonus = min(0.15, category_count * 0.05)
    return float(min(1.0, round(base + bonus, 4)))


def calculate_priority_score(
    composite_integrity: float,
    observed_recovery_ratio: float,
    structural_validity: float,
    recovered_bytes: int,
    sensitivity_level: SensitivityLevel,
    category_count: int,
    ambiguous: bool = False,
    corruption_estimate: float = 0.0,
    weights: Optional[Dict[str, float]] = None,
) -> Tuple[float, str]:
    """
    Calculate deterministic investigative priority score and factual reason.
    
    Combines:
        + integrity contribution (composite_integrity)
        + recoverability contribution (observed_recovery_ratio)
        + structural validity contribution (structural_validity)
        + sensitivity contribution (sensitivity_level + categories)
        + size contribution (recovered_bytes)
        - ambiguity penalty
        - corruption penalty
        
    Strictly bounded in [0.0, 1.0].
    """
    w_dict = weights or {}
    w_integ = float(w_dict.get("integrity", getattr(settings, "PRIORITY_INTEGRITY_WEIGHT", 0.25)))
    w_recov = float(w_dict.get("recoverability", getattr(settings, "PRIORITY_RECOVERABILITY_WEIGHT", 0.20)))
    w_struct = float(w_dict.get("structural", getattr(settings, "PRIORITY_STRUCTURAL_WEIGHT", 0.15)))
    w_sens = float(w_dict.get("sensitivity", getattr(settings, "PRIORITY_SENSITIVITY_WEIGHT", 0.30)))
    w_size = float(w_dict.get("size", getattr(settings, "PRIORITY_SIZE_WEIGHT", 0.10)))

    # Normalize positive weights
    sum_w = w_integ + w_recov + w_struct + w_sens + w_size
    if sum_w <= 0:
        w_integ, w_recov, w_struct, w_sens, w_size = 0.25, 0.20, 0.15, 0.30, 0.10
        sum_w = 1.0

    norm_integ = w_integ / sum_w
    norm_recov = w_recov / sum_w
    norm_struct = w_struct / sum_w
    norm_sens = w_sens / sum_w
    norm_size = w_size / sum_w

    # Components
    c_integ = max(0.0, min(1.0, float(composite_integrity)))
    c_recov = max(0.0, min(1.0, float(observed_recovery_ratio)))
    c_struct = max(0.0, min(1.0, float(structural_validity)))
    c_sens = calculate_sensitivity_component(sensitivity_level, category_count)
    
    norm_bytes_scale = float(getattr(settings, "PRIORITY_SIZE_NORMALIZATION_BYTES", 65536.0))
    c_size = max(0.0, min(1.0, float(recovered_bytes) / max(1.0, norm_bytes_scale)))

    positive_score = (
        (norm_integ * c_integ)
        + (norm_recov * c_recov)
        + (norm_struct * c_struct)
        + (norm_sens * c_sens)
        + (norm_size * c_size)
    )

    # Penalties
    ambig_pen = float(getattr(settings, "PRIORITY_AMBIGUITY_PENALTY", 0.15)) if ambiguous else 0.0
    corr_pen = float(getattr(settings, "PRIORITY_CORRUPTION_PENALTY", 0.10)) * max(0.0, min(1.0, float(corruption_estimate)))

    raw_priority = positive_score - ambig_pen - corr_pen
    priority_score = float(max(0.0, min(1.0, round(raw_priority, 4))))

    # Deterministic factual explanation
    reasons = []
    if priority_score >= 0.70:
        priority_label = "High"
    elif priority_score >= 0.40:
        priority_label = "Medium"
    else:
        priority_label = "Low"

    reasons.append(f"{priority_label} investigative priority (score: {priority_score:.4f}).")

    if sensitivity_level != SensitivityLevel.NONE:
        reasons.append(f"Contains {sensitivity_level.value} sensitivity data across {category_count} category(ies).")
    else:
        reasons.append("Zero sensitive patterns detected.")

    if c_struct >= 1.0:
        reasons.append("File candidate is structurally valid.")
    elif c_struct > 0.0:
        reasons.append(f"Structural validity is {c_struct:.2f}.")
    else:
        reasons.append("Structural validation failed.")

    reasons.append(f"Observed recovery ratio is {c_recov * 100:.1f}%.")

    if ambiguous:
        reasons.append("Ambiguity penalty applied due to tied fragment orderings.")
    if corr_pen > 0.02:
        reasons.append(f"Corruption penalty applied ({corruption_estimate * 100:.1f}% estimated corruption).")

    priority_reason = " ".join(reasons)
    return priority_score, priority_reason


def rank_reconstructed_candidates(candidates: List[ReconstructedFile]) -> List[ReconstructedFile]:
    """
    Sort candidates deterministically by priority_score descending.
    
    Tie-breaking order:
        1. composite_integrity_score (descending)
        2. observed_recovery_ratio (descending)
        3. recovered_bytes (descending)
        4. candidate_id (ascending for deterministic string sort)
    """
    return sorted(
        candidates,
        key=lambda r: (
            -r.priority_score,
            -r.composite_integrity_score,
            -r.observed_recovery_ratio,
            -r.recovered_bytes,
            r.candidate_id or r.id,
        ),
    )
