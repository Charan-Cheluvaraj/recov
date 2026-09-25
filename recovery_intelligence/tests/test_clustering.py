import pytest
from recovery.clustering import cluster_fragments

def test_clustering_interface():
    with pytest.raises(NotImplementedError):
        cluster_fragments([])
