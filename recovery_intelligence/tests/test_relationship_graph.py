# tests/test_relationship_graph.py — Stage 4 Relationship Graph acceptance tests.

import math
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recovery.relationship_graph import (
    calculate_cosine_similarity,
    calculate_offset_proximity,
    calculate_type_compatibility,
    calculate_edge_weight,
    build_relationship_graph,
)
from models.fragment import Fragment
from models.feature_vector import FeatureVector


# 1. Cosine similarity of identical normalized vectors
def test_cosine_similarity_identical():
    v = [1.0 / math.sqrt(64)] * 64
    sim = calculate_cosine_similarity(v, v)
    assert abs(sim - 1.0) < 0.001, f"Expected 1.0, got {sim}"


# 2. Cosine similarity of orthogonal vectors
def test_cosine_similarity_orthogonal():
    v1 = [1.0] + [0.0] * 63
    v2 = [0.0, 1.0] + [0.0] * 62
    sim = calculate_cosine_similarity(v1, v2)
    assert abs(sim - 0.0) < 0.001, f"Expected 0.0, got {sim}"


# 3. Zero-vector safety (no NaN / inf)
def test_cosine_similarity_zero_vector():
    zero = [0.0] * 64
    v = [1.0] + [0.0] * 63
    assert calculate_cosine_similarity(zero, v) == 0.0
    assert calculate_cosine_similarity(zero, zero) == 0.0


# 4. Similarity determinism
def test_similarity_determinism():
    v1 = [0.5, 0.5, 0.5, 0.5] + [0.0] * 60
    v2 = [0.1, 0.2, 0.3, 0.4] + [0.0] * 60
    sim1 = calculate_cosine_similarity(v1, v2)
    sim2 = calculate_cosine_similarity(v1, v2)
    assert sim1 == sim2


# 5. Pairwise similarity excludes self-pairs
def test_graph_excludes_self_pairs():
    f1 = Fragment(id="f1", offset=0, length=512, type_hint="jpeg", source="test.dd")
    f2 = Fragment(id="f2", offset=512, length=512, type_hint="jpeg", source="test.dd")
    fv1 = FeatureVector(fragment_id="f1", vector=[1.0] + [0.0] * 63, dimension=64)
    fv2 = FeatureVector(fragment_id="f2", vector=[1.0] + [0.0] * 63, dimension=64)

    graph = build_relationship_graph([f1, f2], [fv1, fv2], min_weight=0.0)
    for edge in graph["edges"]:
        assert edge["source"] != edge["target"]


# 6-9. Relationship edge components
def test_relationship_edge_components():
    f1 = Fragment(id="f1", offset=0, length=512, type_hint="jpeg", source="test.dd")
    f2 = Fragment(id="f2", offset=512, length=512, type_hint="jpeg", source="test.dd")
    fv1 = FeatureVector(fragment_id="f1", vector=[1.0] + [0.0] * 63, dimension=64)
    fv2 = FeatureVector(fragment_id="f2", vector=[1.0] + [0.0] * 63, dimension=64)

    graph = build_relationship_graph([f1, f2], [fv1, fv2], min_weight=0.0)
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]

    assert "similarity" in edge
    assert "offset_proximity" in edge
    assert "type_match" in edge
    assert "edge_weight" in edge
    assert "reason" in edge

    assert edge["similarity"] == 1.0
    assert edge["offset_proximity"] == 1.0  # adjacent
    assert edge["type_match"] == 1.0       # jpeg == jpeg
    assert edge["edge_weight"] == 1.0


# 10. Edge weight determinism
def test_edge_weight_deterministic():
    w1 = calculate_edge_weight(0.85, 0.50, 1.0)
    w2 = calculate_edge_weight(0.85, 0.50, 1.0)
    assert w1 == w2


# 11-12. Type compatibility
def test_type_compatibility_signals():
    f_jpeg1 = Fragment(id="j1", offset=0, length=512, type_hint="jpeg")
    f_jpeg2 = Fragment(id="j2", offset=1000, length=512, type_hint="jpeg")
    f_pdf = Fragment(id="p1", offset=2000, length=512, type_hint="pdf")

    # Identical types get 1.0
    assert calculate_type_compatibility(f_jpeg1, f_jpeg2) == 1.0
    # Incompatible distinct types get 0.0
    assert calculate_type_compatibility(f_jpeg1, f_pdf) == 0.0