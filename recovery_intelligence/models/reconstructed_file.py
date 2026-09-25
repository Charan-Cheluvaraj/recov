from pydantic import BaseModel, Field
from typing import List, Dict, Any

class ReconstructedFile(BaseModel):
    """Candidate file reconstructed from fragment clusters with four-signal scoring metrics."""
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

    # Stage 7 Recoverability Fields
    candidate_id: str = ""
    output_path: str = ""
    output_sha256: str = ""
    fragment_count: int = 0
    recovered_bytes: int = 0
    gap_count: int = 0
    missing_or_unknown_bytes: int = 0
    observed_candidate_span: int = 0
    observed_recovery_ratio: float = 0.0
    recovery_status: str = "UNRECOVERABLE"
    recovery_reason: str = ""

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


