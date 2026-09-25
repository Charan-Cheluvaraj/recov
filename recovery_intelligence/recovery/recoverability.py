import os
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from config.settings import settings
from models.fragment import Fragment
from models.reconstructed_file import ReconstructedFile
from models.recoverability import RecoveryStatus, RecoverabilityAssessment
from recovery.reconstruction import EXTENSION_MAP
from recovery.text_reconstruction import read_fragment_bytes


def calculate_recoverability_metrics(
    recovered_bytes: int,
    missing_or_unknown_bytes: int,
    gap_count: int,
    fragment_count: int,
) -> Dict[str, Any]:
    """
    Calculate deterministic recoverability metrics.
    
    Definitions:
        recovered_bytes: exact number of fragment bytes written into candidate.
        missing_or_unknown_bytes: sum of gaps between associated fragments.
        observed_candidate_span: recovered_bytes + missing_or_unknown_bytes.
        observed_recovery_ratio: recovered_bytes / observed_candidate_span.
        
    IMPORTANT:
    This ratio reflects the fraction of the observed candidate span represented
    by recovered bytes. It MUST NOT be described as 'percentage of original file'
    unless original file size is independently observable.
    """
    rec_b = max(0, int(recovered_bytes))
    mis_b = max(0, int(missing_or_unknown_bytes))
    obs_span = rec_b + mis_b

    if obs_span > 0:
        ratio = round(rec_b / obs_span, 4)
    elif rec_b > 0:
        ratio = 1.0
    else:
        ratio = 0.0

    return {
        "recovered_bytes": rec_b,
        "missing_or_unknown_bytes": mis_b,
        "gap_count": max(0, int(gap_count)),
        "fragment_count": max(0, int(fragment_count)),
        "observed_candidate_span": obs_span,
        "observed_recovery_ratio": ratio,
    }


def determine_recovery_status(
    structural_validity: float,
    gap_count: int,
    recovered_bytes: int,
    fragment_count: int,
    file_type: str = "unknown",
    ambiguous: bool = False,
    status: str = "",
) -> RecoveryStatus:
    """
    Determine deterministic recovery status based strictly on observable evidence.
    
    Status mapping:
        - UNRECOVERABLE: no valid reconstruction candidate produced (0 bytes or cluster only)
        - AMBIGUOUS: multiple plausible fragment orderings/groupings exist
        - RAW_BINARY_RECOVERY: unvalidated raw binary payload with no structured format validation
        - FULLY_RECONSTRUCTED: 0 gaps, parser validation succeeded
        - STRUCTURALLY_VALID_PARTIAL: parser validation succeeded (partial/tolerant structure)
        - PARTIALLY_RECONSTRUCTED: internal gaps exist, parser validation failed
        - STRUCTURALLY_INVALID: no gaps or assembled stream failed parser validation
    """
    st_lower = (status or "").lower()
    if st_lower == "cluster_only" or (fragment_count <= 0 and recovered_bytes <= 0):
        return RecoveryStatus.UNRECOVERABLE

    if ambiguous or st_lower == "ambiguous":
        return RecoveryStatus.AMBIGUOUS

    if structural_validity >= 1.0:
        if gap_count == 0:
            return RecoveryStatus.FULLY_RECONSTRUCTED
        else:
            return RecoveryStatus.STRUCTURALLY_VALID_PARTIAL

    ft_lower = (file_type or "").lower()
    if ft_lower in ("raw", "bin"):
        return RecoveryStatus.RAW_BINARY_RECOVERY

    if gap_count > 0:
        return RecoveryStatus.PARTIALLY_RECONSTRUCTED
    else:
        return RecoveryStatus.STRUCTURALLY_INVALID


def generate_recovery_reason(
    fragment_count: int,
    recovered_bytes: int,
    observed_candidate_span: int,
    missing_bytes: int,
    file_type: str,
    structural_validity: float,
    recovery_status: str,
    parser_message: str = "",
) -> str:
    """
    Generate concise, machine-generated factual summary without speculation or LLM.
    """
    if recovery_status in (RecoveryStatus.UNRECOVERABLE.value, "UNRECOVERABLE") or recovered_bytes == 0:
        return (
            f"Candidate has no recoverable bytes or fragment members. "
            f"Structural validation is not possible. Classified as UNRECOVERABLE."
        )

    parts = []
    frag_word = "fragment" if fragment_count == 1 else "associated fragments"
    parts.append(f"Candidate reconstructed from {fragment_count} {frag_word}.")
    parts.append(f"{recovered_bytes:,} bytes were recovered across a {observed_candidate_span:,}-byte observed span.")

    if missing_bytes > 0:
        parts.append(f"{missing_bytes:,} bytes remain missing or unknown between associated fragments.")
    else:
        parts.append("No internal gaps were observed between associated fragments.")

    ft_upper = file_type.upper() if file_type and file_type != "unknown" else "Format"
    if recovery_status in (RecoveryStatus.RAW_BINARY_RECOVERY.value, "RAW_BINARY_RECOVERY"):
        parts.append("File type not structurally validated; preserved as raw binary salvage.")
    elif structural_validity >= 1.0:
        parts.append(f"{ft_upper} structural validation succeeded.")
    else:
        msg = f" ({parser_message})" if parser_message else ""
        parts.append(f"{ft_upper} structural validation failed{msg}.")

    parts.append(f"The candidate is therefore classified as {recovery_status}.")
    return " ".join(parts)


def write_recovered_artifact(
    candidate_id: str,
    file_type: str,
    candidate_bytes: bytes,
    recovery_status: Optional[RecoveryStatus] = None,
    output_dir: Optional[Path] = None,
) -> Tuple[Path, str]:
    """
    Write candidate bytes to disk at appropriate subdirectory:
        recovered/validated/recovered_<candidate_id>.<ext>
        recovered/partial/recovery_candidate_<candidate_id>.<ext>
        recovered/invalid/invalid_candidate_<candidate_id>.<ext>
        recovered/raw/raw_candidate_<candidate_id>.bin
        
    Never overwrites original evidence.
    """
    base_out = output_dir or settings.RECOVERED_DIR
    ext = EXTENSION_MAP.get((file_type or "").lower().strip().lstrip("."), ".bin")

    if recovery_status in (RecoveryStatus.FULLY_RECONSTRUCTED, RecoveryStatus.STRUCTURALLY_VALID_PARTIAL):
        sub_dir = base_out / "validated"
        artifact_name = f"recovered_{candidate_id}{ext}"
    elif recovery_status == RecoveryStatus.PARTIALLY_RECONSTRUCTED:
        sub_dir = base_out / "partial"
        artifact_name = f"recovery_candidate_{candidate_id}{ext}"
    elif recovery_status == RecoveryStatus.RAW_BINARY_RECOVERY:
        sub_dir = base_out / "raw"
        artifact_name = f"raw_candidate_{candidate_id}{ext}"
    elif recovery_status is not None:
        sub_dir = base_out / "invalid"
        artifact_name = f"invalid_candidate_{candidate_id}{ext}"
    else:
        sub_dir = base_out
        artifact_name = f"recovered_{candidate_id}{ext}"

    sub_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = sub_dir / artifact_name

    with open(artifact_path, "wb") as f:
        f.write(candidate_bytes)

    # Also maintain top-level copy for backward compatibility if in a sub_dir
    if sub_dir != base_out:
        top_path = base_out / f"recovered_{candidate_id}{ext}"
        try:
            if not top_path.exists():
                with open(top_path, "wb") as tf:
                    tf.write(candidate_bytes)
        except Exception:
            pass

    sha256_hash = hashlib.sha256(candidate_bytes).hexdigest()
    return artifact_path, sha256_hash


def assess_recoverability(
    reconstructed_file: ReconstructedFile,
    fragments: Optional[List[Fragment]] = None,
    output_dir: Optional[Path] = None,
) -> ReconstructedFile:
    """
    Perform Stage 7 recoverability assessment on a ReconstructedFile.
    
    1. Computes union byte coverage, unique recovered bytes, and missing/unknown gap bytes.
    2. Writes the candidate artifact to categorized subdirectories in recovered/.
    3. Computes the SHA-256 of the generated artifact.
    4. Deterministically assigns recovery status and concise factual explanation.
    """
    frag_map = {f.id: f for f in fragments} if fragments else {}
    cand_id = reconstructed_file.candidate_id or reconstructed_file.id
    
    # 1. Gather fragment bytes
    cand_fragments: List[Fragment] = []
    raw_chunks: List[bytes] = []

    for fid in reconstructed_file.fragment_ids:
        if fid in frag_map:
            frag = frag_map[fid]
            cand_fragments.append(frag)
            chunk = read_fragment_bytes(frag)
            raw_chunks.append(chunk)

    # If raw_chunks is empty but candidate file was already generated:
    if not raw_chunks and reconstructed_file.status != "cluster_only":
        ext = EXTENSION_MAP.get(reconstructed_file.file_type.lower(), ".bin")
        stage5_path = (output_dir or settings.RECOVERED_DIR) / f"{cand_id}{ext}"
        if stage5_path.exists():
            with open(stage5_path, "rb") as sf:
                c_bytes = sf.read()
                raw_chunks.append(c_bytes)

    assembled_candidate_bytes = b"".join(raw_chunks)
    
    # Compute union coverage
    if cand_fragments:
        from recovery.text_reconstruction import compute_union_coverage
        coverage = compute_union_coverage(cand_fragments)
        recovered_bytes = coverage["unique_recovered_bytes"]
        total_gap_bytes = coverage["total_gap_bytes"]
        gap_count = coverage["gap_count"]
        source_ranges = coverage["source_ranges"]
        source_offsets = coverage["source_offsets"]
        overlap_bytes = coverage["overlap_bytes"]
        raw_fragment_bytes = coverage["raw_fragment_bytes"]
    else:
        recovered_bytes = len(assembled_candidate_bytes)
        gap_info = reconstructed_file.gap_information or {}
        total_gap_bytes = int(gap_info.get("total_gap_bytes", 0))
        gap_count = int(gap_info.get("gap_count", 0))
        source_ranges = reconstructed_file.source_ranges or []
        source_offsets = reconstructed_file.source_offsets or []
        overlap_bytes = reconstructed_file.overlap_bytes or 0
        raw_fragment_bytes = reconstructed_file.raw_fragment_bytes or recovered_bytes

    fragment_count = len(reconstructed_file.fragment_ids)

    # 2. Calculate recoverability metrics
    metrics = calculate_recoverability_metrics(
        recovered_bytes=recovered_bytes,
        missing_or_unknown_bytes=total_gap_bytes,
        gap_count=gap_count,
        fragment_count=fragment_count,
    )

    # 3. Determine recovery status
    rec_status = determine_recovery_status(
        structural_validity=reconstructed_file.structural_validity,
        gap_count=gap_count,
        recovered_bytes=recovered_bytes,
        fragment_count=fragment_count,
        file_type=reconstructed_file.file_type,
        ambiguous=reconstructed_file.ambiguous,
        status=reconstructed_file.status,
    )

    # 4. Write recovered candidate artifact if bytes exist
    out_dir = output_dir or settings.RECOVERED_DIR
    if assembled_candidate_bytes:
        artifact_path, artifact_sha = write_recovered_artifact(
            candidate_id=cand_id,
            file_type=reconstructed_file.file_type,
            candidate_bytes=assembled_candidate_bytes,
            recovery_status=rec_status,
            output_dir=out_dir,
        )
        out_path_str = str(artifact_path.resolve())
        artifact_exists = True
    else:
        out_path_str = ""
        artifact_sha = ""
        artifact_exists = False

    # 5. Generate factual machine-generated explanation
    reason = generate_recovery_reason(
        fragment_count=fragment_count,
        recovered_bytes=recovered_bytes,
        observed_candidate_span=metrics["observed_candidate_span"],
        missing_bytes=total_gap_bytes,
        file_type=reconstructed_file.file_type,
        structural_validity=reconstructed_file.structural_validity,
        recovery_status=rec_status.value,
        parser_message=reconstructed_file.parser_message,
    )

    is_valid_recovery = rec_status in (RecoveryStatus.FULL_RECOVERY, RecoveryStatus.VALIDATED_RECOVERY)

    # 6. Update ReconstructedFile model
    reconstructed_file.candidate_id = cand_id
    reconstructed_file.output_path = out_path_str
    reconstructed_file.output_sha256 = artifact_sha
    reconstructed_file.artifact_path = out_path_str
    reconstructed_file.artifact_sha256 = artifact_sha
    reconstructed_file.artifact_exists = artifact_exists
    reconstructed_file.fragment_count = fragment_count
    reconstructed_file.source_offsets = source_offsets
    reconstructed_file.source_ranges = source_ranges
    reconstructed_file.raw_fragment_bytes = raw_fragment_bytes
    reconstructed_file.unique_recovered_bytes = recovered_bytes
    reconstructed_file.recovered_bytes = recovered_bytes
    reconstructed_file.overlap_bytes = overlap_bytes
    reconstructed_file.duplicate_bytes = overlap_bytes
    reconstructed_file.gap_count = gap_count
    reconstructed_file.missing_or_unknown_bytes = total_gap_bytes
    reconstructed_file.observed_candidate_span = metrics["observed_candidate_span"]
    reconstructed_file.observed_recovery_ratio = metrics["observed_recovery_ratio"]
    reconstructed_file.recovery_status = rec_status.value
    reconstructed_file.recovery_state = rec_status.value
    reconstructed_file.is_validated_recovery = is_valid_recovery
    reconstructed_file.recovery_reason = reason

    return reconstructed_file
