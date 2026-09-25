# tests/test_fingerprinting_stage3.py — Stage 3 acceptance tests.

import builtins
import hashlib
import math
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recovery.fingerprinting import (
    fingerprint_binary_fragment,
    fingerprint_text_fragment,
    fingerprint_fragment,
    fit_and_fingerprint,
    normalize_vector,
    _text_tfidf_fallback,
)
from models.fragment import Fragment
from models.feature_vector import FeatureVector
from pipeline import run_stage_3


def _make_fragment(data: bytes, tmp_path: Path, fid: str = "frag-f1", char: str = "binary") -> Fragment:
    ev = tmp_path / f"{fid}.dd"
    ev.write_bytes(data)
    return Fragment(
        id=fid,
        offset=0,
        length=len(data),
        type_hint="unknown",
        source=str(ev),
        pipeline_tag="characterized",
        metadata={"characterization": char},
    )


# 1. Binary fingerprint function works
def test_binary_fingerprint_works():
    data = b"\x00\xFF\xAA\x55" * 64
    fv = fingerprint_binary_fragment(data, "frag-b1")
    assert isinstance(fv, FeatureVector)
    assert fv.fragment_id == "frag-b1"
    assert fv.dimension == 64
    assert len(fv.vector) == 64


# 2. Text fingerprint function works
def test_text_fingerprint_works():
    text = "Digital evidence recovery and fragment reconstruction pipeline."
    fv = fingerprint_text_fragment(text, "frag-t1")
    assert isinstance(fv, FeatureVector)
    assert fv.fragment_id == "frag-t1"
    assert fv.dimension == 64
    assert len(fv.vector) == 64


# 3. Output is deterministic
def test_fingerprint_deterministic():
    data = b"Sample binary payload 12345"
    fv1 = fingerprint_binary_fragment(data)
    fv2 = fingerprint_binary_fragment(data)
    assert fv1.vector == fv2.vector

    text = "Deterministic sentence test"
    tv1 = fingerprint_text_fragment(text)
    tv2 = fingerprint_text_fragment(text)
    assert tv1.vector == tv2.vector


# 4. Output dimension is 64
def test_dimension_is_64():
    fv = fingerprint_binary_fragment(b"\x12\x34\x56\x78")
    assert fv.dimension == 64
    assert len(fv.vector) == 64

    tv = fingerprint_text_fragment("Short text")
    assert tv.dimension == 64
    assert len(tv.vector) == 64


# 5. L2 norm is approx 1 for non-zero vectors
def test_l2_norm_is_one():
    data = b"Arbitrary non-zero test sequence 1234567890"
    fv = fingerprint_binary_fragment(data)
    norm = math.sqrt(sum(x * x for x in fv.vector))
    assert abs(norm - 1.0) < 0.01, f"Expected L2 norm ~1.0, got {norm}"


# 6. Zero vector is handled safely
def test_zero_vector_handled_safely():
    zeros = [0.0] * 64
    norm_zeros = normalize_vector(zeros)
    assert norm_zeros == [0.0] * 64
    assert not any(math.isnan(x) or math.isinf(x) for x in norm_zeros)


# 7. Short binary data does not crash
def test_short_binary_data_no_crash():
    for short_data in [b"", b"\x00", b"\x01\x02"]:
        fv = fingerprint_binary_fragment(short_data)
        assert len(fv.vector) == 64
        assert not any(math.isnan(x) or math.isinf(x) for x in fv.vector)


# 8. Text model loading is lazy
def test_text_model_loading_lazy(monkeypatch):
    import recovery.fingerprinting as fp
    monkeypatch.setattr(fp, "_SENTENCE_TRANSFORMER_LOAD_ATTEMPTED", False)
    monkeypatch.setattr(fp, "_SENTENCE_TRANSFORMER_MODEL", None)
    assert not fp._SENTENCE_TRANSFORMER_LOAD_ATTEMPTED
    fp.get_sentence_transformer()
    assert fp._SENTENCE_TRANSFORMER_LOAD_ATTEMPTED


# 9-10. Transformer / Fallback method reporting
def test_fingerprint_method_metadata():
    fv_bin = fingerprint_binary_fragment(b"\x00\x01\x02\x03" * 10)
    assert fv_bin.metadata.get("fingerprint_method") == "binary_2gram_tfidf_svd"

    text_fallback_vec = _text_tfidf_fallback("Sample text")
    assert len(text_fallback_vec) == 64


# 11. Binary fragments use binary fingerprinting
def test_binary_fragment_uses_binary_method(tmp_path):
    frag = _make_fragment(b"\x00\xFF\xFE\xFD" * 32, tmp_path, "b-frag", char="binary")
    fv = fingerprint_fragment(frag)
    assert fv.metadata.get("fingerprint_method") == "binary_2gram_tfidf_svd"


# 12. Text fragments use text fingerprinting
def test_text_fragment_uses_text_method(tmp_path):
    frag = _make_fragment(b"The quick brown fox jumps over the lazy dog", tmp_path, "t-frag", char="text")
    fv = fingerprint_fragment(frag)
    assert fv.metadata.get("fingerprint_method") in ("text_minilm_embedding", "text_tfidf_fallback")


# 13. Mixed fragments follow documented policy (binary path)
def test_mixed_fragment_uses_binary_method(tmp_path):
    frag = _make_fragment(b"Text portion " + b"\x00\xFF" * 32, tmp_path, "m-frag", char="mixed")
    fv = fingerprint_fragment(frag)
    assert fv.metadata.get("fingerprint_method") == "binary_2gram_tfidf_svd"


# 14. FeatureVector model is populated correctly
def test_feature_vector_model_populated(tmp_path):
    frag = _make_fragment(b"Test bytes", tmp_path, "frag-pv")
    fv = fingerprint_fragment(frag)
    assert fv.fragment_id == "frag-pv"
    assert isinstance(fv.vector, list)
    assert fv.dimension == 64
    assert "fingerprint_method" in fv.metadata


# 15-17. All returned vectors contain finite numeric values (no NaN, no Infinity)
def test_vectors_contain_finite_values(tmp_path):
    frags = [
        _make_fragment(b"", tmp_path, "empty-frag", "binary"),
        _make_fragment(b"hello world", tmp_path, "text-frag", "text"),
        _make_fragment(b"\xFF\xD8\xFF\xE0" * 20, tmp_path, "bin-frag", "binary"),
    ]
    fvs = fit_and_fingerprint(frags)
    for fv in fvs:
        for val in fv.vector:
            assert isinstance(val, (int, float))
            assert not math.isnan(val), f"NaN found in vector for {fv.fragment_id}"
            assert not math.isinf(val), f"Infinity found in vector for {fv.fragment_id}"


# 18. run_stage_3() works
@pytest.fixture
def synthetic_evidence(tmp_path) -> str:
    buf = bytearray(4096)
    buf[0:2] = b"\xFF\xD8"
    buf[2:200] = b"Sample JPEG header and printable text fragment metadata block " * 3
    buf[512:512 + 256] = bytes(range(256))
    ev = tmp_path / "synthetic_stage3.dd"
    ev.write_bytes(bytes(buf))
    return str(ev)


def test_run_stage_3_returns_evidence_fragments_features(synthetic_evidence):
    evidence, fragments, features = run_stage_3(synthetic_evidence)
    assert evidence is not None
    assert isinstance(fragments, list)
    assert isinstance(features, list)
    assert len(features) == len(fragments)
    for fv in features:
        assert fv.dimension == 64
        assert len(fv.vector) == 64


# 19. Evidence bytes remain unchanged
def test_evidence_bytes_unchanged_stage3(synthetic_evidence):
    with open(synthetic_evidence, "rb") as f:
        pre_bytes = f.read()
    run_stage_3(synthetic_evidence)
    with open(synthetic_evidence, "rb") as f:
        post_bytes = f.read()
    assert pre_bytes == post_bytes


# 20. ground_truth.json is never accessed
def test_ground_truth_never_accessed_stage3(synthetic_evidence, monkeypatch):
    real_open = builtins.open
    accessed = []

    def guarded_open(file, *args, **kwargs):
        if Path(str(file)).name == "ground_truth.json":
            accessed.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    run_stage_3(synthetic_evidence)
    assert not accessed, f"ground_truth.json accessed: {accessed}"