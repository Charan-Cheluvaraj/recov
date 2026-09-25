import pytest
from recovery.reconstruction import reconstruct_structured_file
from models import FragmentCluster, ReconstructedFile

def test_reconstruction_interface():
    cluster = FragmentCluster(cluster_id="c1", inferred_type="jpeg")
    recon = reconstruct_structured_file(cluster, [])
    assert isinstance(recon, ReconstructedFile)
    assert recon.cluster_id == "c1"
    assert recon.status == "cluster_only"
