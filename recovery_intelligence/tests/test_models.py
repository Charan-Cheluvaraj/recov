import pytest
from pydantic import ValidationError
from models import Fragment, FeatureVector, FragmentCluster, ReconstructedFile, RankedResults, Evidence, Narrative

def test_models_instantiation():
    frag = Fragment(id="f1", offset=0, length=512, type_hint="jpeg")
    assert frag.id == "f1"
    assert frag.entropy == 0.0

    fv = FeatureVector(fragment_id="f1", vector=[0.1, 0.2], dimension=2)
    assert fv.dimension == 2

    cluster = FragmentCluster(cluster_id="c1", member_fragment_ids=["f1"])
    assert len(cluster.member_fragment_ids) == 1

    recon = ReconstructedFile(id="r1", cluster_id="c1", file_type="jpeg")
    assert recon.status == "candidate"

    ranked = RankedResults(evidence_image_hash="abc123hash", files=[recon])
    assert len(ranked.files) == 1

    ev = Evidence(
        evidence_id="EV-1234567890AB",
        source_path="/evidence/test_image.dd",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        created_at="2026-09-25T16:30:00Z",
        metadata={"file_name": "test_image.dd", "size_bytes": 1024},
    )
    assert ev.evidence_id == "EV-1234567890AB"
    assert ev.source_path == "/evidence/test_image.dd"
    assert ev.sha256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert ev.metadata["size_bytes"] == 1024

    narr = Narrative(observed=["File carved"], inferred=["JPEG type"], unknown=["Gap at 0x100"])
    assert len(narr.observed) == 1

def test_evidence_model_validation():
    """Verify Evidence model strictly enforces required fields."""
    with pytest.raises(ValidationError):
        # Missing required sha256 and created_at
        Evidence(evidence_id="E1", source_path="test.dd")  # type: ignore
