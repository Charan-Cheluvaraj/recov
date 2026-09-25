from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RecoveryStatus(str, Enum):
    """Deterministic recoverability statuses based strictly on observable evidence."""
    FULLY_RECONSTRUCTED = "FULLY_RECONSTRUCTED"
    PARTIALLY_RECONSTRUCTED = "PARTIALLY_RECONSTRUCTED"
    STRUCTURALLY_VALID_PARTIAL = "STRUCTURALLY_VALID_PARTIAL"
    STRUCTURALLY_INVALID = "STRUCTURALLY_INVALID"
    AMBIGUOUS = "AMBIGUOUS"
    UNRECOVERABLE = "UNRECOVERABLE"


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
    recovered_bytes: int = 0
    gap_count: int = 0
    missing_or_unknown_bytes: int = 0
    observed_candidate_span: int = 0
    observed_recovery_ratio: float = 0.0
    
    # Preserved Stage 5 & 6 metrics
    structural_validity: float = 0.0
    reconstruction_confidence: float = 0.0
    completeness: float = 0.0
    corruption_estimate: float = 0.0
    composite_integrity_score: float = 0.0
    
    # Deterministic recovery status & machine-generated explanation
    recovery_status: RecoveryStatus = RecoveryStatus.UNRECOVERABLE
    recovery_reason: str = ""
