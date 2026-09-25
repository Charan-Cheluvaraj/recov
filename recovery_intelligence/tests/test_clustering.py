import pytest
from recovery.clustering import cluster_fragments
from models.feature_vector import FeatureVector

def test_clustering_interface():
    clusters, orphans = cluster_fragments([])
    assert clusters == []
    assert orphans == []

    # Single feature vector becomes orphan when min_samples=2
    fv = FeatureVector(fragment_id="f1", vector=[1.0] + [0.0] * 63, dimension=64)
    clusters, orphans = cluster_fragments([fv], min_samples=2)
    assert len(clusters) == 0
    assert orphans == ["f1"]