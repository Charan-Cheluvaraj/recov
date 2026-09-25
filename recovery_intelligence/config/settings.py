import os
from pathlib import Path
from pydantic import BaseModel, Field

class Settings(BaseModel):
    """Application settings and configuration paths."""
    
    # Project Paths
    BASE_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    EVIDENCE_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "evidence")
    RECOVERED_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "recovered")
    CACHE_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "cache")
    RESULTS_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "results")
    DATASET_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "dataset")
    
    # Carving & Fragment Settings
    DEFAULT_FRAGMENT_SIZE: int = 512
    MAX_EVIDENCE_SIZE_MB: int = 1024
    
    # AI Models
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    LLM_PROVIDER: str = "gemini"  # "gemini" or "anthropic"
    
    # Thresholds
    ENTROPY_HIGH_THRESHOLD: float = 7.5
    ENTROPY_LOW_THRESHOLD: float = 3.0
    SIMILARITY_THRESHOLD: float = 0.75
    
    class Config:
        arbitrary_types_allowed = True

settings = Settings()
