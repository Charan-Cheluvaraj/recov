import os
from pydantic import BaseModel

class FeatureFlags(BaseModel):
    """Feature flags to enable/disable optional components safely."""
    
    ENABLE_FAISS: bool = True
    ENABLE_PYTSK3: bool = False  # Optional raw file-system parser
    ENABLE_PRESIDIO_YARA: bool = True
    ENABLE_SENTENCE_TRANSFORMER: bool = True
    ENABLE_LLM: bool = False
    ENABLE_GRAPHVIZ: bool = True

feature_flags = FeatureFlags(
    ENABLE_FAISS=os.getenv("ENABLE_FAISS", "true").lower() == "true",
    ENABLE_PYTSK3=os.getenv("ENABLE_PYTSK3", "false").lower() == "true",
    ENABLE_PRESIDIO_YARA=os.getenv("ENABLE_PRESIDIO_YARA", "true").lower() == "true",
    ENABLE_SENTENCE_TRANSFORMER=os.getenv("ENABLE_SENTENCE_TRANSFORMER", "true").lower() == "true",
    ENABLE_LLM=os.getenv("ENABLE_LLM", "false").lower() == "true",
    ENABLE_GRAPHVIZ=os.getenv("ENABLE_GRAPHVIZ", "true").lower() == "true",
)
