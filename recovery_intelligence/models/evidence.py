from pydantic import BaseModel, Field
from typing import Dict, Any

class Evidence(BaseModel):
    """Metadata tracking raw storage image or evidence file under analysis."""
    evidence_id: str
    source_path: str
    sha256: str
    created_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
