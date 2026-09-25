import pytest
from recovery.reconstruction import reconstruct_structured_file
from models import FragmentCluster

def test_reconstruction_interface():
    cluster = FragmentCluster(cluster_id="c1")
    with pytest.raises(NotImplementedError):
        reconstruct_structured_file(cluster, [])
