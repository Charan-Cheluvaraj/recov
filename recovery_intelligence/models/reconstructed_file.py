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
