from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class RecoveryStatus(str, Enum):
    """
    Explicit, unambiguous forensic recovery states.
    Distinguishes raw carved fragments, proposed candidates, validated files, and salvage.
    """
    FULLY_RECONSTRUCTED = "FULLY_RECONSTRUCTED"
    STRUCTURALLY_VALID_PARTIAL = "STRUCTURALLY_VALID_PARTIAL"
    PARTIALLY_RECONSTRUCTED = "PARTIALLY_RECONSTRUCTED"
    STRUCTURALLY_INVALID = "STRUCTURALLY_INVALID"
    RAW_BINARY_RECOVERY = "RAW_BINARY_RECOVERY"
    AMBIGUOUS = "AMBIGUOUS"
    UNRECOVERABLE = "UNRECOVERABLE"
    CARVED_FRAGMENT = "CARVED_FRAGMENT"
    RECONSTRUCTION_CANDIDATE = "RECONSTRUCTION_CANDIDATE"

    # Forward & backward compatible aliases
    FULL_RECOVERY = "FULLY_RECONSTRUCTED"
    VALIDATED_RECOVERY = "STRUCTURALLY_VALID_PARTIAL"
    PARTIAL_RECONSTRUCTION = "PARTIALLY_RECONSTRUCTED"
    INVALID_RECONSTRUCTION = "STRUCTURALLY_INVALID"
    AMBIGUOUS_CANDIDATE = "AMBIGUOUS"


class RecoveryConfidence(str, Enum):
    """Forensic inference confidence levels."""
    DIRECT_EVIDENCE = "DIRECT_EVIDENCE"
    STRONG_INFERENCE = "STRONG_INFERENCE"
    WEAK_INFERENCE = "WEAK_INFERENCE"


class RecoverabilityAssessment(BaseModel):
    """
    Recoverability assessment record for a reconstruction candidate.
    
    Quantifies exact recovered bytes vs missing/unknown gap bytes without
    speculating on unobservable original file size.
    """
    candidate_id: str
    output_path: str = ""
    output_sha256: str = ""
    file_type: str = "unknown"
    fragment_ids: List[str] = Field(default_factory=list)
    fragment_count: int = 0
    source_offsets: List[int] = Field(default_factory=list)
    source_ranges: List[List[int]] = Field(default_factory=list)
    
    raw_fragment_bytes: int = 0
    unique_recovered_bytes: int = 0
    overlap_bytes: int = 0
    gap_count: int = 0
    missing_or_unknown_bytes: int = 0
    observed_candidate_span: int = 0
    observed_recovery_ratio: float = 0.0
    
    known_original_size: Optional[int] = None
    logical_recovery_ratio: Optional[float] = None
    logical_recovery_ratio_available: bool = False
    
    # Structural parser validation metrics
    structural_validity: float = 0.0
    parser_validation_status: str = "NOT_VALIDATED"
    parser_message: str = ""
    is_validated_recovery: bool = False
    
    # Preserved Stage 5 & 6 metrics
    reconstruction_confidence: float = 0.0
    completeness: float = 0.0
    corruption_estimate: float = 0.0
    composite_integrity_score: float = 0.0
    
    # Deterministic recovery status & machine-generated explanation
    recovery_status: str = "UNRECOVERABLE"
    recovery_state: str = "UNRECOVERABLE"
    recovery_confidence: str = "WEAK_INFERENCE"
    recovery_reason: str = ""
    ground_truth_used: bool = False
