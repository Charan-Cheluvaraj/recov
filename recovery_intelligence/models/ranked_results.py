from pydantic import BaseModel, Field
from typing import List
from .reconstructed_file import ReconstructedFile
from .cluster import FragmentCluster
from .fragment import Fragment

class RankedResults(BaseModel):
    """Complete ranked execution output containing recovered files, clusters, and orphan fragments."""
    evidence_image_hash: str
    files: List[ReconstructedFile] = Field(default_factory=list)
    clusters: List[FragmentCluster] = Field(default_factory=list)
    orphans: List[Fragment] = Field(default_factory=list)
