from typing import List
from models.feature_vector import FeatureVector

def fingerprint_binary_fragment(data: bytes) -> FeatureVector:
    """Generate n-gram byte frequency and structural feature vector for binary data."""
    raise NotImplementedError("fingerprint_binary_fragment is deferred in Prompt 1.")

def fingerprint_text_fragment(text: str) -> FeatureVector:
    """Generate TF-IDF / embedding feature vector for text data."""
    raise NotImplementedError("fingerprint_text_fragment is deferred in Prompt 1.")

def normalize_vector(vector: List[float]) -> List[float]:
    """Normalize vector to unit length (L2 norm)."""
    raise NotImplementedError("normalize_vector is deferred in Prompt 1.")
