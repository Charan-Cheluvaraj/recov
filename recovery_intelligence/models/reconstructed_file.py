from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ReconstructedFile(BaseModel):
    """
    Forensic candidate file reconstructed from fragment clusters with
    independent four-signal integrity scoring and strict structural validation status.
    """
    id: str
    cluster_id: str
    file_type: str = "unknown"
    fragment_ids: List[str] = Field(default_factory=list)
    gap_information: Dict[str, Any] = Field(default_factory=dict)
    
    # Four-signal scoring
    reconstruction_confidence: float = 0.0
    completeness: float = 0.0
    structural_validity: float = 0.0
    corruption_estimate: float = 0.0
    
    # Derived composite scores
    composite_integrity_score: float = 0.0
    priority_score: float = 0.0
    
    # Intelligence metadata
    sensitivity_hits: List[Dict[str, Any]] = Field(default_factory=list)
    ambiguous: bool = False
    status: str = "candidate"  # e.g., "candidate", "validated", "corrupted", "failed"
    parser_message: str = ""

    # Comprehensive Candidate & Fragment Coverage Fields
    candidate_id: str = ""
    source_offsets: List[int] = Field(default_factory=list)
    source_ranges: List[List[int]] = Field(default_factory=list)
    raw_fragment_bytes: int = 0
    unique_recovered_bytes: int = 0
    overlap_bytes: int = 0
    duplicate_bytes: int = 0
    fragment_count: int = 0
    recovered_bytes: int = 0
    gap_count: int = 0
    missing_or_unknown_bytes: int = 0
    observed_candidate_span: int = 0
    observed_recovery_ratio: float = 0.0

    # Logical File Recovery Fields (from filesystem metadata when available)
    known_original_size: Optional[int] = None
    logical_recovery_ratio: Optional[float] = None
    logical_recovery_ratio_available: bool = False

    # Parser & Recovery Verification State
    parser_validation_status: str = "NOT_VALIDATED"
    is_validated_recovery: bool = False
    recovery_status: str = ""
    recovery_state: str = ""
    recovery_confidence: str = "WEAK_INFERENCE"
    recovery_reason: str = ""
    candidate_generation_reason: str = ""
    reconstruction_reason: str = ""
    validation_reason: str = ""
    ground_truth_used: bool = False

    # Artifact Storage
    output_path: str = ""
    output_sha256: str = ""
    artifact_path: str = ""
    artifact_sha256: str = ""
    artifact_exists: bool = False

    # Stage 8 Sensitivity & Investigative Priority Fields
    sensitivity_level: str = "NONE"
    detected_categories: List[str] = Field(default_factory=list)
    sensitivity_matches: List[Dict[str, Any]] = Field(default_factory=list)
    priority_reason: str = ""

    def __init__(self, **data: Any):
        super().__init__(**data)
        if not self.candidate_id and self.id:
            self.candidate_id = self.id
        if not self.fragment_count and self.fragment_ids:
            self.fragment_count = len(self.fragment_ids)
        if not self.artifact_path and self.output_path:
            self.artifact_path = self.output_path
        if not self.output_path and self.artifact_path:
            self.output_path = self.artifact_path
        if not self.artifact_sha256 and self.output_sha256:
            self.artifact_sha256 = self.output_sha256
        if not self.output_sha256 and self.artifact_sha256:
            self.output_sha256 = self.artifact_sha256
        if not self.recovered_bytes and self.unique_recovered_bytes:
            self.recovered_bytes = self.unique_recovered_bytes
        if not self.unique_recovered_bytes and self.recovered_bytes:
            self.unique_recovered_bytes = self.recovered_bytes
        if not self.recovery_state and self.recovery_status:
            self.recovery_state = self.recovery_status
        elif not self.recovery_status and self.recovery_state:
            self.recovery_status = self.recovery_state
        elif not self.recovery_state and not self.recovery_status:
            self.recovery_state = "UNRECOVERABLE"
            self.recovery_status = "UNRECOVERABLE"

    @property
    def is_successfully_recovered(self) -> bool:
        """True ONLY if real parser structural validation succeeded."""
        return (
            self.structural_validity >= 1.0
            and self.recovery_state in (
                "FULL_RECOVERY",
                "VALIDATED_RECOVERY",
                "FULLY_RECONSTRUCTED",
                "STRUCTURALLY_VALID_PARTIAL",
            )
        )
