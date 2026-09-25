from pydantic import BaseModel, Field
from typing import List

class Narrative(BaseModel):
    """Structured investigative report explicitly separating empirical observations from AI inferences."""
    observed: List[str] = Field(default_factory=list)
    inferred: List[str] = Field(default_factory=list)
    unknown: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    generated_text: str = ""
