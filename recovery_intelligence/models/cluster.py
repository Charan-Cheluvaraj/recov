from pydantic import BaseModel, Field
from typing import List

class FragmentCluster(BaseModel):
    """Cluster of related fragments grouped by structure or semantic similarity."""
    cluster_id: str
    member_fragment_ids: List[str] = Field(default_factory=list)
    inferred_type: str = "unknown"
    confidence: float = 0.0
    reason: str = ""
