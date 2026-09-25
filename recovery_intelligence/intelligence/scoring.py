from typing import List, Dict, Any, Optional
from config.settings import settings
from models.reconstructed_file import ReconstructedFile
from models.cluster import FragmentCluster
from models.fragment import Fragment


def calculate_reconstruction_confidence(
    fragment_relationships: Optional[Dict[str, Any]] = None,
    *,
    cluster_confidence: float = 0.0,
    member_count: int = 1,
    ambiguous: bool = False,
    status: str = "reconstructed",
    **kwargs,
) -> float:
    """
    Calculate relationship & ordering confidence signal (0.0 to 1.0).
    
    Represents how strongly the observed fragment relationships, clustering confidence,
    and reconstruction evidence support this candidate grouping/ordering.
    
    This is an engineering confidence metric, NOT a statistical probability.
    """
    if fragment_relationships:
        cluster_confidence = float(fragment_relationships.get("cluster_confidence", cluster_confidence))
        member_count = int(fragment_relationships.get("member_count", member_count))
        ambiguous = bool(fragment_relationships.get("ambiguous", ambiguous))
        status = str(fragment_relationships.get("status", status))

    # Base confidence by reconstruction status
    st = (status or "").lower()
    if st == "cluster_only" or member_count <= 0:
        base = 0.10
    elif st == "validation_failed":
        base = 0.40
    elif st == "ambiguous":
        base = 0.45
    elif st == "reconstructed":
        base = 0.70
    else:
        base = 0.50

    # Cluster confidence contribution (up to +0.20)
    cl_contrib = 0.20 * min(1.0, max(0.0, float(cluster_confidence)))
    score = base + cl_contrib

    # Member count adjustments: single fragment has no ordering ambiguity risk (+0.10)
    if member_count == 1 and st == "reconstructed":
        score += 0.10

    # Ambiguity penalty: if candidate has tied/ambiguous ordering evidence
    if ambiguous or st == "ambiguous":
        score = min(score, 0.45)
        score *= 0.75

    # Strictly clamp to [0.0, 1.0]
    return float(max(0.0, min(1.0, round(score, 4))))


def calculate_completeness(
    expected_size: int = 0,
    actual_size: int = 0,
    missing_gaps: int = 0,
    *,
    gap_information: Optional[Dict[str, Any]] = None,
    header_flag: bool = False,
    footer_flag: bool = False,
    **kwargs,
) -> float:
    """
    Calculate file completeness signal (0.0 to 1.0).
    
    Represents how much of the candidate's expected/observed structure appears
    to be present based on fragment byte coverage, detected non-contiguous gaps,
    and structural boundary markers (headers/footers).
    """
    total_gap_bytes = 0
    gap_count = missing_gaps

    if gap_information:
        gap_count = int(gap_information.get("gap_count", gap_count))
        total_gap_bytes = int(gap_information.get("total_gap_bytes", 0))

    if expected_size > 0 and actual_size > 0 and total_gap_bytes == 0:
        total_gap_bytes = max(0, expected_size - actual_size)

    # Empty candidate
    if actual_size <= 0 and not gap_information and expected_size == 0 and missing_gaps == 0:
        return 0.0

    # Byte coverage calculation
    if actual_size > 0:
        denom = actual_size + total_gap_bytes
        byte_ratio = actual_size / denom if denom > 0 else 1.0
    else:
        # Unknown size but gap count known
        byte_ratio = 1.0 if gap_count == 0 else max(0.2, 1.0 - (gap_count * 0.15))

    # Gap count penalty (penalty for fragment discontinuity)
    gap_penalty = min(0.35, gap_count * 0.07)
    score = byte_ratio * (1.0 - gap_penalty)

    # Header and footer bonus if both structural boundaries are present with 0 gaps
    if header_flag and footer_flag and gap_count == 0:
        score = min(1.0, score + 0.05)

    return float(max(0.0, min(1.0, round(score, 4))))


def calculate_structural_validity(
    parser_success: bool,
    parser_errors: Optional[List[str]] = None,
    *,
    parser_message: str = "",
    status: str = "",
    **kwargs,
) -> float:
    """
    Calculate structural validity signal based on real parser checks (0.0 to 1.0).
    
    Grounded strictly in Stage 5 parser results (Pillow, pypdf/PyPDF2, python-docx,
    zipfile, sqlite3, or text validation).
    
    Parser success demonstrates valid format syntax, but does not prove authenticity
    or complete original content.
    """
    if (status or "").lower() == "cluster_only":
        return 0.0

    if parser_success:
        # Full parser validation passed
        if parser_errors and len(parser_errors) > 0:
            # Non-fatal warnings reported
            return 0.90
        return 1.0
    else:
        # Parser failed
        msg = (parser_message or "").lower()
        if "missing" in msg and ("soi" in msg or "magic" in msg or "header" in msg):
            return 0.0
        return 0.0


def calculate_corruption_estimate(
    entropy_anomalies: int = 0,
    invalid_sectors: int = 0,
    *,
    parser_success: bool = True,
    parser_message: str = "",
    gap_count: int = 0,
    status: str = "reconstructed",
    **kwargs,
) -> float:
    """
    Calculate corruption estimate signal (0.0 to 1.0).
    
    Scale convention:
        0.0 = no estimated corruption (clean candidate)
        1.0 = high estimated corruption (severely damaged/corrupted candidate)
        
    Note: Gaps alone reflect missing content (completeness), NOT corruption.
    Corruption measures damaged, malformed, or invalid bytes/syntax.
    """
    st = (status or "").lower()
    if st == "cluster_only":
        return 0.0

    if not parser_success or st == "validation_failed":
        # Base corruption for failed parser validation
        base_corruption = 0.75
        msg = (parser_message or "").lower()
        if any(term in msg for term in ("crc", "badzipfile", "corrupt", "unidentified", "databaseerror")):
            base_corruption = 0.90
        score = base_corruption
    else:
        # Succeeded validation: baseline clean
        score = 0.0

    # Additive anomalies
    anomaly_contrib = min(0.20, int(entropy_anomalies) * 0.05)
    sector_contrib = min(0.20, int(invalid_sectors) * 0.05)
    score += anomaly_contrib + sector_contrib

    return float(max(0.0, min(1.0, round(score, 4))))


def calculate_composite_integrity(
    confidence: float,
    completeness: float,
    validity: float,
    corruption: float,
    *,
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    Calculate transparent composite integrity score purely for candidate prioritization & sorting.
    
    Combines:
        weighted(confidence, completeness, validity, 1.0 - corruption)
        
    Weights are configurable via settings or kwargs.
    """
    w_dict = weights or {}
    w_conf = float(w_dict.get("reconstruction_confidence", getattr(settings, "RECONSTRUCTION_CONFIDENCE_WEIGHT", 0.25)))
    w_comp = float(w_dict.get("completeness", getattr(settings, "COMPLETENESS_WEIGHT", 0.25)))
    w_val = float(w_dict.get("structural_validity", getattr(settings, "STRUCTURAL_VALIDITY_WEIGHT", 0.35)))
    w_corr = float(w_dict.get("corruption", getattr(settings, "CORRUPTION_WEIGHT", 0.15)))

    # Ensure non-negative
    w_conf = max(0.0, w_conf)
    w_comp = max(0.0, w_comp)
    w_val = max(0.0, w_val)
    w_corr = max(0.0, w_corr)

    total_weight = w_conf + w_comp + w_val + w_corr
    if total_weight <= 0.0:
        w_conf, w_comp, w_val, w_corr = 0.25, 0.25, 0.35, 0.15
        total_weight = 1.0

    # Normalize weights
    norm_conf = w_conf / total_weight
    norm_comp = w_comp / total_weight
    norm_val = w_val / total_weight
    norm_corr = w_corr / total_weight

    # Bounded inputs
    c = max(0.0, min(1.0, float(confidence)))
    cp = max(0.0, min(1.0, float(completeness)))
    v = max(0.0, min(1.0, float(validity)))
    cr = max(0.0, min(1.0, float(corruption)))

    # Corruption is inverted: 0 corruption -> 1.0 integrity
    integrity_from_corruption = 1.0 - cr

    composite = (
        (norm_conf * c)
        + (norm_comp * cp)
        + (norm_val * v)
        + (norm_corr * integrity_from_corruption)
    )

    return float(max(0.0, min(1.0, round(composite, 4))))


def score_reconstructed_file(
    file_record: ReconstructedFile,
    cluster: Optional[FragmentCluster] = None,
    fragments: Optional[List[Fragment]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> ReconstructedFile:
    """
    Score a ReconstructedFile candidate across the four independent signals
    and derive the composite integrity score.
    """
    member_count = len(file_record.fragment_ids)
    cluster_conf = cluster.confidence if cluster else 0.0

    # 1. Reconstruction confidence
    rel_info = {
        "cluster_confidence": cluster_conf,
        "member_count": member_count,
        "ambiguous": file_record.ambiguous,
        "status": file_record.status,
    }
    r_conf = calculate_reconstruction_confidence(
        rel_info,
        cluster_confidence=cluster_conf,
        member_count=member_count,
        ambiguous=file_record.ambiguous,
        status=file_record.status,
    )

    # 2. Completeness
    gap_info = file_record.gap_information or {}
    has_header = False
    has_footer = False
    actual_bytes = 0
    if fragments:
        frag_map = {f.id: f for f in fragments}
        for fid in file_record.fragment_ids:
            if fid in frag_map:
                f = frag_map[fid]
                actual_bytes += f.length
                if f.header_flag:
                    has_header = True
                if f.footer_flag:
                    has_footer = True

    comp = calculate_completeness(
        actual_size=actual_bytes,
        gap_information=gap_info,
        header_flag=has_header,
        footer_flag=has_footer,
    )

    # 3. Structural validity
    parser_success = file_record.status == "reconstructed" or file_record.structural_validity >= 1.0
    s_val = calculate_structural_validity(
        parser_success=parser_success,
        parser_message=file_record.parser_message,
        status=file_record.status,
    )

    # 4. Corruption estimate
    corr = calculate_corruption_estimate(
        parser_success=parser_success,
        parser_message=file_record.parser_message,
        gap_count=gap_info.get("gap_count", 0),
        status=file_record.status,
    )

    # 5. Composite integrity
    comp_score = calculate_composite_integrity(
        confidence=r_conf,
        completeness=comp,
        validity=s_val,
        corruption=corr,
        weights=weights,
    )

    # Update candidate record
    file_record.reconstruction_confidence = r_conf
    file_record.completeness = comp
    file_record.structural_validity = s_val
    file_record.corruption_estimate = corr
    file_record.composite_integrity_score = comp_score

    return file_record
