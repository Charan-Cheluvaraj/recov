# tests/test_entropy.py — Stage 2 acceptance tests.

import builtins
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recovery.entropy import (
    calculate_entropy,
    calculate_printable_ratio,
    analyze_entropy_windows,
    characterize_fragment,
)
from models.fragment import Fragment
from pipeline import run_stage_2


def _make_fragment(data: bytes, tmp_path: Path, fid: str = "frag-test") -> Fragment:
    ev = tmp_path / f"{fid}.dd"
    ev.write_bytes(data)
    return Fragment(
        id=fid,
        offset=0,
        length=len(data),
        type_hint="unknown",
        source=str(ev),
        pipeline_tag="carved",
    )


def _text_bytes(n: int = 512) -> bytes:
    sentence = b"The quick brown fox jumps over the lazy dog. "
    repeats = (n // len(sentence)) + 1
    return (sentence * repeats)[:n]


def _binary_bytes(n: int = 512) -> bytes:
    result = bytearray()
    counter = 0
    while len(result) < n:
        block = hashlib.sha256(f"binary_seed_{counter}".encode()).digest()
        result.extend(block)
        counter += 1
    return bytes(result[:n])


def _mixed_bytes(text_n: int = 512, binary_n: int = 512) -> bytes:
    return _text_bytes(text_n) + _binary_bytes(binary_n)


def test_empty_data_entropy_is_zero():
    assert calculate_entropy(b"") == 0.0


def test_repeated_byte_zero_entropy():
    assert calculate_entropy(b"\x00" * 512) == 0.0
    assert calculate_entropy(b"\xFF" * 1024) == 0.0


def test_known_two_byte_entropy():
    data = b"\x00\xFF" * 128
    e = calculate_entropy(data)
    assert abs(e - 1.0) < 0.001, f"Expected ~1.0, got {e}"


def test_diverse_bytes_near_max_entropy():
    data = bytes(range(256))
    e = calculate_entropy(data)
    assert e > 7.9, f"Expected entropy close to 8.0, got {e}"


@pytest.mark.parametrize("data", [
    b"",
    b"\x00" * 100,
    bytes(range(256)),
    _text_bytes(300),
    _binary_bytes(300),
    _mixed_bytes(200, 200),
])
def test_entropy_always_in_range(data):
    e = calculate_entropy(data)
    assert 0.0 <= e <= 8.0


def test_entropy_deterministic():
    data = _binary_bytes(512)
    assert calculate_entropy(data) == calculate_entropy(data)


def test_window_boundaries_correct():
    data = bytes(range(256)) * 2
    windows = analyze_entropy_windows(data, window_size=128, step_size=64)
    assert windows
    for w in windows:
        assert w["start"] >= 0
        assert w["end"] <= len(data)
        assert w["end"] > w["start"]
        assert (w["end"] - w["start"]) <= 128


def test_step_size_respected():
    data = bytes(range(256)) * 4
    windows = analyze_entropy_windows(data, window_size=128, step_size=64)
    if len(windows) >= 2:
        for i in range(1, len(windows)):
            gap = windows[i]["start"] - windows[i - 1]["start"]
            assert gap == 64 or windows[i]["end"] == len(data)


def test_window_results_deterministic():
    data = _mixed_bytes(256, 256)
    w1 = analyze_entropy_windows(data, window_size=64, step_size=32)
    w2 = analyze_entropy_windows(data, window_size=64, step_size=32)
    assert w1 == w2


def test_printable_ratio_deterministic():
    data = _text_bytes(256)
    assert calculate_printable_ratio(data) == calculate_printable_ratio(data)


def test_printable_ratio_all_printable():
    assert calculate_printable_ratio(b"Hello World") == 1.0


def test_printable_ratio_no_printable():
    assert calculate_printable_ratio(bytes([0x00, 0x01, 0x02] * 64)) == 0.0


def test_printable_ratio_includes_whitespace():
    assert calculate_printable_ratio(b"\t\n\r " * 50) == 1.0


def test_printable_ratio_empty():
    assert calculate_printable_ratio(b"") == 0.0


def test_text_characterization(tmp_path):
    data = _text_bytes(512)
    frag = _make_fragment(data, tmp_path, "frag-text")
    result = characterize_fragment(frag)
    assert result.metadata["characterization"] == "text"


def test_binary_characterization(tmp_path):
    data = _binary_bytes(512)
    frag = _make_fragment(data, tmp_path, "frag-binary")
    result = characterize_fragment(frag)
    assert result.metadata["characterization"] == "binary"


def test_mixed_characterization(tmp_path):
    data = _text_bytes(512) + _binary_bytes(512)
    frag = _make_fragment(data, tmp_path, "frag-mixed")
    result = characterize_fragment(frag)
    char = result.metadata["characterization"]
    assert char in ("mixed", "binary"), f"Expected mixed/binary, got {char}"


def test_fragment_entropy_updated(tmp_path):
    data = bytes(range(256)) * 2
    frag = _make_fragment(data, tmp_path, "frag-ent")
    assert frag.entropy == 0.0
    result = characterize_fragment(frag)
    expected = calculate_entropy(data)
    assert abs(result.entropy - expected) < 0.001
    assert result.entropy > 0.0


def test_fragment_metadata_keys(tmp_path):
    data = _text_bytes(256)
    frag = _make_fragment(data, tmp_path, "frag-meta")
    result = characterize_fragment(frag)
    for key in ("characterization", "printable_ratio", "entropy_window_size",
                "entropy_step_size", "entropy_windows"):
        assert key in result.metadata, f"Missing metadata key: {key}"


def test_fragment_pipeline_tag_characterized(tmp_path):
    frag = _make_fragment(_text_bytes(128), tmp_path, "frag-tag")
    assert characterize_fragment(frag).pipeline_tag == "characterized"


def test_no_raw_bytes_in_metadata(tmp_path):
    frag = _make_fragment(_binary_bytes(256), tmp_path, "frag-nb")
    result = characterize_fragment(frag)
    for key, value in result.metadata.items():
        assert not isinstance(value, (bytes, bytearray)), f"Key '{key}' has raw bytes"
    for window in result.metadata.get("entropy_windows", []):
        for wk, wv in window.items():
            assert not isinstance(wv, (bytes, bytearray)), f"Window key '{wk}' has raw bytes"


@pytest.fixture
def synthetic_evidence(tmp_path) -> str:
    buf = bytearray(4096)
    buf[0:2] = b"\xFF\xD8"
    text_payload = _text_bytes(128)
    buf[2:2 + len(text_payload)] = text_payload
    buf[512:512 + 256] = _binary_bytes(256)
    ev = tmp_path / "synthetic.dd"
    ev.write_bytes(bytes(buf))
    return str(ev)


def test_run_stage_2_returns_evidence_and_fragments(synthetic_evidence):
    evidence, fragments = run_stage_2(synthetic_evidence)
    assert evidence is not None
    assert isinstance(fragments, list)


def test_run_stage_2_fragments_characterized(synthetic_evidence):
    _, fragments = run_stage_2(synthetic_evidence)
    for frag in fragments:
        assert frag.pipeline_tag == "characterized"
        assert "characterization" in frag.metadata
        assert frag.entropy >= 0.0


def test_evidence_sha256_unchanged(synthetic_evidence):
    with open(synthetic_evidence, "rb") as f:
        pre_hash = hashlib.sha256(f.read()).hexdigest()
    evidence, _ = run_stage_2(synthetic_evidence)
    with open(synthetic_evidence, "rb") as f:
        post_hash = hashlib.sha256(f.read()).hexdigest()
    assert pre_hash == post_hash
    assert evidence.sha256 == pre_hash


def test_original_evidence_bytes_unchanged(synthetic_evidence):
    with open(synthetic_evidence, "rb") as f:
        original = f.read()
    run_stage_2(synthetic_evidence)
    with open(synthetic_evidence, "rb") as f:
        after = f.read()
    assert original == after


def test_ground_truth_never_accessed(synthetic_evidence, monkeypatch):
    real_open = builtins.open
    accessed = []

    def guarded_open(file, *args, **kwargs):
        if Path(str(file)).name == "ground_truth.json":
            accessed.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    run_stage_2(synthetic_evidence)
    assert not accessed, f"ground_truth.json accessed: {accessed}"