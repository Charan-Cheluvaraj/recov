# tests/test_clustering_stage4.py — Stage 4 Clustering acceptance tests.

import builtins
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recovery.clustering import cluster_fragments
from models.fragment import Fragment
from models.feature_vector import FeatureVector
from models.cluster import FragmentCluster
from pipeline import run_stage_4


# 13. DBSCAN creates clusters for clearly similar data
def test_dbscan_creates_clusters():
    # 3 identical vectors A (should cluster together)
    # 2 orthogonal vectors B (distinct cluster)
    v_a = [1.0] + [0.0] * 63
    v_b = [0.0, 1.0] + [0.0] * 62

    fvs = [
        FeatureVector(fragment_id="a1", vector=v_a, dimension=64),
        FeatureVector(fragment_id="a2", vector=v_a, dimension=64),
        FeatureVector(fragment_id="a3", vector=v_a, dimension=64),
        FeatureVector(fragment_id="b1", vector=v_b, dimension=64),
        FeatureVector(fragment_id="b2", vector=v_b, dimension=64),
    ]

    clusters, orphans = cluster_fragments(fvs, eps=0.3, min_samples=2)
    assert len(clusters) == 2
    assert len(orphans) == 0

    c1_members = clusters[0].member_fragment_ids
    c2_members = clusters[1].member_fragment_ids

    assert ("a1" in c1_members and "a2" in c1_members and "a3" in c1_members) or \
           ("a1" in c2_members and "a2" in c2_members and "a3" in c2_members)


# 14. DBSCAN preserves noise as orphan
def test_dbscan_preserves_orphans():
    v_cluster = [1.0] + [0.0] * 63
    v_isolated = [0.0] * 63 + [1.0]

    fvs = [
        FeatureVector(fragment_id="c1", vector=v_cluster, dimension=64),
        FeatureVector(fragment_id="c2", vector=v_cluster, dimension=64),
        FeatureVector(fragment_id="isolated_orphan", vector=v_isolated, dimension=64),
    ]

    clusters, orphans = cluster_fragments(fvs, eps=0.3, min_samples=2)
    assert len(clusters) == 1
    assert "isolated_orphan" in orphans


# 15. Cluster member IDs are correct
def test_cluster_member_ids_correct():
    v = [1.0] + [0.0] * 63
    fvs = [
        FeatureVector(fragment_id="frag_101", vector=v, dimension=64),
        FeatureVector(fragment_id="frag_102", vector=v, dimension=64),
    ]
    clusters, _ = cluster_fragments(fvs, eps=0.3, min_samples=2)
    assert len(clusters) == 1
    assert set(clusters[0].member_fragment_ids) == {"frag_101", "frag_102"}


# 16-17. Inferred type and reason existence
def test_cluster_inferred_type_and_reason():
    v = [1.0] + [0.0] * 63
    fvs = [
        FeatureVector(fragment_id="f1", vector=v, dimension=64),
        FeatureVector(fragment_id="f2", vector=v, dimension=64),
    ]
    frags = [
        Fragment(id="f1", offset=0, length=512, type_hint="pdf"),
        Fragment(id="f2", offset=512, length=512, type_hint="pdf"),
    ]

    clusters, _ = cluster_fragments(fvs, fragments=frags, eps=0.3, min_samples=2)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.inferred_type == "pdf"
    assert c.confidence > 0.0
    assert len(c.reason) > 0
    assert "pdf" in c.reason


# 18. run_stage_4() works on test evidence
@pytest.fixture
def synthetic_evidence(tmp_path) -> str:
    buf = bytearray(4096)
    buf[0:2] = b"\xFF\xD8"
    buf[2:300] = b"JPEG fragment sample text content payload " * 5
    buf[512:512 + 256] = bytes(range(256))
    ev = tmp_path / "synthetic_stage4.dd"
    ev.write_bytes(bytes(buf))
    return str(ev)


def test_run_stage_4_returns_structured_results(synthetic_evidence):
    evidence, fragments, features, graph, clusters, orphans = run_stage_4(synthetic_evidence)
    assert evidence is not None
    assert isinstance(fragments, list)
    assert isinstance(features, list)
    assert isinstance(graph, dict)
    assert "nodes" in graph
    assert "edges" in graph
    assert isinstance(clusters, list)
    assert isinstance(orphans, list)


# 19. Evidence remains unchanged
def test_evidence_bytes_unchanged_stage4(synthetic_evidence):
    with open(synthetic_evidence, "rb") as f:
        pre_bytes = f.read()
    run_stage_4(synthetic_evidence)
    with open(synthetic_evidence, "rb") as f:
        post_bytes = f.read()
    assert pre_bytes == post_bytes


# 20. ground_truth.json is never accessed
def test_ground_truth_never_accessed_stage4(synthetic_evidence, monkeypatch):
    real_open = builtins.open
    accessed = []

    def guarded_open(file, *args, **kwargs):
        if Path(str(file)).name == "ground_truth.json":
            accessed.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    run_stage_4(synthetic_evidence)
    assert not accessed, f"ground_truth.json accessed: {accessed}"