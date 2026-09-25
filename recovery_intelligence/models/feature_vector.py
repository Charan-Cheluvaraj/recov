from pydantic import BaseModel, Field
from typing import List, Dict, Any

class FeatureVector(BaseModel):
    """Numerical feature representation of a fragment for clustering & semantic analysis."""
    fragment_id: str
    vector: List[float] = Field(default_factory=list)
    dimension: int = 64
    metadata: Dict[str, Any] = Field(default_factory=dict)