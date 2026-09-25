from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from .evidence import Evidence
from .fragment import Fragment
from .feature_vector import FeatureVector
from .cluster import FragmentCluster
from .reconstructed_file import ReconstructedFile
from .ranked_results import RankedResults


class PipelineResult(BaseModel):
    """Authoritative complete execution output of the end-to-end recovery pipeline."""
    pipeline_version: str = "1.0.0"
    evidence_path: str = ""
    evidence_sha256: str = ""
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_duration: float = 0.0
    stage_durations: Dict[str, float] = Field(default_factory=dict)
    cached: bool = False
    
    evidence: Optional[Evidence] = None
    fragments: List[Fragment] = Field(default_factory=list)
    characterized_fragments: List[Fragment] = Field(default_factory=list)
    feature_vectors: List[FeatureVector] = Field(default_factory=list)
    relationship_graph: Dict[str, Any] = Field(default_factory=dict)
    clusters: List[FragmentCluster] = Field(default_factory=list)
    orphans: List[str] = Field(default_factory=list)
    reconstructed_files: List[ReconstructedFile] = Field(default_factory=list)
    recoverability_results: List[Dict[str, Any]] = Field(default_factory=list)
    sensitivity_results: List[Dict[str, Any]] = Field(default_factory=list)
    ranked_results: Optional[RankedResults] = None
    final_summary: str = ""

    def ensure_ranked_results(self) -> RankedResults:
        """Ensure ranked_results is populated from reconstructed_files if not already set."""
        if self.ranked_results is None:
            orphan_objs = [f for f in self.fragments if f.id in self.orphans]
            self.ranked_results = RankedResults(
                evidence_image_hash=self.evidence_sha256,
                files=self.reconstructed_files,
                clusters=self.clusters,
                orphans=orphan_objs,
            )
        return self.ranked_results
