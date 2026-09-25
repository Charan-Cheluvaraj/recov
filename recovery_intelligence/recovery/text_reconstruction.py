from typing import List
from models.cluster import FragmentCluster
from models.fragment import Fragment
from models.reconstructed_file import ReconstructedFile

def reconstruct_small_text_cluster(cluster: FragmentCluster, fragments: List[Fragment]) -> ReconstructedFile:
    """Reconstruct small text file from fragment cluster using exact overlap/order."""
    raise NotImplementedError("reconstruct_small_text_cluster is deferred in Prompt 1.")

def reconstruct_large_text_cluster(cluster: FragmentCluster, fragments: List[Fragment]) -> ReconstructedFile:
    """Reconstruct large text file using semantic embedding alignment and fragment ordering."""
    raise NotImplementedError("reconstruct_large_text_cluster is deferred in Prompt 1.")
