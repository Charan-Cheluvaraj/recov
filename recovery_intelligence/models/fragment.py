from pydantic import BaseModel, Field
from typing import Dict, Any

class Fragment(BaseModel):
    """Represents a carved memory/disk fragment."""
    id: str
    offset: int
    length: int
    type_hint: str = "unknown"
    entropy: float = 0.0
    source: str = ""
    pipeline_tag: str = "raw"
    header_flag: bool = False
    footer_flag: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
