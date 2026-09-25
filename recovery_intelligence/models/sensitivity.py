from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class SensitivityLevel(str, Enum):
    """Deterministic sensitivity levels based on observable data patterns."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SensitivityMatch(BaseModel):
    """Observable sensitive pattern match descriptor with redacted snippet."""
    category: str
    pattern_name: str
    match_snippet: str
    occurrence_count: int = 1


class SensitivityAssessment(BaseModel):
    """
    Deterministic sensitivity classification assessment for a recovered candidate.
    
    Contains strictly observable pattern detections without claiming real identity.
    """
    candidate_id: str
    sensitivity_level: SensitivityLevel = SensitivityLevel.NONE
    detected_categories: List[str] = Field(default_factory=list)
    matches: List[SensitivityMatch] = Field(default_factory=list)
    match_count: int = 0
    explanation: str = ""
