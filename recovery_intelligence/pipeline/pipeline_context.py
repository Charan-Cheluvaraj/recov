from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from models import (
    Fragment,
    FeatureVector,
    FragmentCluster,
    ReconstructedFile,
    Evidence,
    Narrative,
    RankedResults,
    PipelineResult,
)

class PipelineContext(BaseModel):
    """Runtime context object carrying artifacts across all 14 pipeline stages."""
    evidence_path: str
    evidence: Optional[Evidence] = None
    fragments: List[Fragment] = Field(default_factory=list)
    features: List[FeatureVector] = Field(default_factory=list)
    relationship_graph: Dict[str, Any] = Field(default_factory=dict)
    clusters: List[FragmentCluster] = Field(default_factory=list)
    orphans: List[str] = Field(default_factory=list)
    reconstructed_files: List[ReconstructedFile] = Field(default_factory=list)
    narrative: Optional[Narrative] = None
    ranked_results: Optional[RankedResults] = None