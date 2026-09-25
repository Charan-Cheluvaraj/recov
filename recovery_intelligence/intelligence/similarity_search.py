from typing import List, Tuple, Any
from models.feature_vector import FeatureVector

def build_similarity_index(features: List[FeatureVector]) -> Any:
    """Build FAISS CPU vector similarity index from fragment feature vectors."""
    raise NotImplementedError("build_similarity_index is deferred in Prompt 1.")

def find_similar(query_vector: List[float], index: Any, top_k: int = 5) -> List[Tuple[str, float]]:
    """Query similarity index for top-k closest fragments."""
    raise NotImplementedError("find_similar is deferred in Prompt 1.")
