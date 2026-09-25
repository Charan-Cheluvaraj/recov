from pydantic import BaseModel, Field
from typing import List

class FeatureVector(BaseModel):
    """Numerical feature representation of a fragment for clustering & semantic analysis."""
    fragment_id: str
    vector: List[float] = Field(default_factory=list)
    dimension: int = 0
