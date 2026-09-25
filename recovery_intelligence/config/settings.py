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
    
    # Stage 2 Entropy & Characterization Settings
    ENTROPY_WINDOW_SIZE: int = 128
    ENTROPY_STEP_SIZE: int = 32
    PRINTABLE_RATIO_TEXT_THRESHOLD: float = 0.85
    PRINTABLE_RATIO_BINARY_THRESHOLD: float = 0.30
    ENTROPY_TEXT_MAX: float = 5.8
    ENTROPY_BINARY_MIN: float = 6.5
    MIXED_ENTROPY_DELTA: float = 1.8
    
    # Stage 3 Fingerprinting & Embedding Settings
    BINARY_TFIDF_NGRAM_RANGE: tuple = (2, 2)
    BINARY_SVD_COMPONENTS: int = 64
    FINGERPRINT_DIMENSION: int = 64
    
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