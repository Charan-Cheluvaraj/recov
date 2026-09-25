from typing import List
from models.feature_vector import FeatureVector
from models.cluster import FragmentCluster

def cluster_fragments(features: List[FeatureVector]) -> List[FragmentCluster]:
    """Group feature vectors into semantic/structural fragment clusters."""
    raise NotImplementedError("cluster_fragments is deferred in Prompt 1.")
