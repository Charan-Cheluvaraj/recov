import io
import os
import hashlib
import tempfile
import zipfile
import sqlite3
import pytest
from pathlib import Path
from PIL import Image

try:
    import docx
except ImportError:
    docx = None

from models.cluster import FragmentCluster
from models.fragment import Fragment
from models.reconstructed_file import ReconstructedFile
from recovery.reconstruction import reconstruct_structured_file
from recovery.text_reconstruction import (
    reconstruct_small_text_cluster,
    reconstruct_large_text_cluster,
    compute_gap_information,
)
from pipeline.orchestrator import run_stage_5


@pytest.fixture
def temp_evidence(tmp_path):
    """Create a temporary multi-fragment binary evidence file."""
    # 1. Create a valid small JPEG
    img = Image.new("RGB", (20, 20), color="green")
    jbuf = io.BytesIO()
    img.save(jbuf, format="JPEG")
    jpeg_bytes = jbuf.getvalue()

    # 2. Evidence layout:
    # 0..200: noise
    # 200..200+len(jpeg_part1): first half of jpeg
    # gap of 100 bytes noise
    # 300+len(jpeg_part1)..end: second half of jpeg
    part1_len = len(jpeg_bytes) // 2
    part1 = jpeg_bytes[:part1_len]
    part2 = jpeg_bytes[part1_len:]

    evidence_bytes = (
        b"\x00" * 200
        + part1
        + b"\xaa" * 100  # 100 byte gap
        + part2
        + b"\x00" * 200
    )

    ev_path = tmp_path / "test_evidence.raw"
    with open(ev_path, "wb") as f:
        f.write(evidence_bytes)

    sha_initial = hashlib.sha256(evidence_bytes).hexdigest()

    f1 = Fragment(
        id="frag_j1",
        offset=200,
        length=part1_len,
        type_hint="jpeg",
        source=str(ev_path),
        header_flag=True,
    )
    f2 = Fragment(
        id="frag_j2",
        offset=200 + part1_len + 100,
        length=len(part2),
        type_hint="jpeg",
        source=str(ev_path),
        footer_flag=True,
    )

    return {
        "path": str(ev_path),
        "sha256": sha_initial,
        "frag1": f1,
        "frag2": f2,
        "jpeg_bytes": jpeg_bytes,
        "part1_len": part1_len,
    }


def test_structured_cluster_ordering_is_deterministic(temp_evidence, tmp_path):
    """Fragments are ordered deterministically by offset regardless of input list order."""
    f1 = temp_evidence["frag1"]
    f2 = temp_evidence["frag2"]
    cluster = FragmentCluster(cluster_id="c_det", inferred_type="jpeg")

    # Pass in reverse order [f2, f1]
    recon = reconstruct_structured_file(cluster, [f2, f1], output_dir=tmp_path)
    assert recon.fragment_ids == ["frag_j1", "frag_j2"]

    # Pass in direct order [f1, f2]
    recon2 = reconstruct_structured_file(cluster, [f1, f2], output_dir=tmp_path)
    assert recon2.fragment_ids == ["frag_j1", "frag_j2"]


def test_jpeg_candidate_assembly_works(temp_evidence, tmp_path):
    """Non-contiguous JPEG fragments are assembled and validated."""
    f1 = temp_evidence["frag1"]
    f2 = temp_evidence["frag2"]
    cluster = FragmentCluster(cluster_id="c_jpeg", inferred_type="jpeg")

    recon = reconstruct_structured_file(cluster, [f1, f2], output_dir=tmp_path)

    assert recon.status == "reconstructed"
    assert recon.structural_validity == 1.0
    assert "JPEG" in recon.parser_message
    assert (tmp_path / "recon_c_jpeg.jpg").exists()

    # Gap information recorded
    assert recon.gap_information["has_gaps"] is True
    assert recon.gap_information["gap_count"] == 1
    assert recon.gap_information["total_gap_bytes"] == 100


def test_pdf_candidate_assembly_works(tmp_path):
    """PDF fragments written and validated using real PDF parser."""
    minimal_pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 10 10]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000052 00000 n 
0000000103 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
164
%%EOF"""

    ev_path = tmp_path / "pdf_ev.raw"
    with open(ev_path, "wb") as f:
        f.write(minimal_pdf)

    frag = Fragment(
        id="frag_pdf1",
        offset=0,
        length=len(minimal_pdf),
        type_hint="pdf",
        source=str(ev_path),
        header_flag=True,
    )
    cluster = FragmentCluster(cluster_id="c_pdf", inferred_type="pdf")

    recon = reconstruct_structured_file(cluster, [frag], output_dir=tmp_path)
    assert recon.status == "reconstructed"
    assert recon.structural_validity == 1.0
    assert "PDF" in recon.parser_message
    assert (tmp_path / "recon_c_pdf.pdf").exists()


def test_zip_and_docx_candidate_assembly_works(tmp_path):
    """ZIP candidate assembly and real parser validation."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test.txt", "Forensics Stage 5")
    zip_bytes = buf.getvalue()

    ev_path = tmp_path / "zip_ev.raw"
    with open(ev_path, "wb") as f:
        f.write(zip_bytes)

    frag = Fragment(
        id="frag_z1",
        offset=0,
        length=len(zip_bytes),
        type_hint="zip",
        source=str(ev_path),
    )
    cluster = FragmentCluster(cluster_id="c_zip", inferred_type="zip")

    recon = reconstruct_structured_file(cluster, [frag], output_dir=tmp_path)
    assert recon.status == "reconstructed"
    assert recon.structural_validity == 1.0
    assert "ZIP" in recon.parser_message
    assert (tmp_path / "recon_c_zip.zip").exists()


def test_sqlite_candidate_assembly_works(tmp_path):
    """SQLite candidate assembly and PRAGMA integrity validation."""
    tf_path = tmp_path / "seed.sqlite"
    conn = sqlite3.connect(str(tf_path))
    conn.execute("CREATE TABLE evidence (id INT);")
    conn.execute("INSERT INTO evidence VALUES (42);")
    conn.commit()
    conn.close()

    with open(tf_path, "rb") as f:
        sql_bytes = f.read()

    ev_path = tmp_path / "sql_ev.raw"
    with open(ev_path, "wb") as f:
        f.write(sql_bytes)

    frag = Fragment(
        id="frag_sq1",
        offset=0,
        length=len(sql_bytes),
        type_hint="sqlite",
        source=str(ev_path),
    )
    cluster = FragmentCluster(cluster_id="c_sql", inferred_type="sqlite")

    recon = reconstruct_structured_file(cluster, [frag], output_dir=tmp_path)
    assert recon.status == "reconstructed"
    assert recon.structural_validity == 1.0
    assert "PRAGMA integrity_check: ok" in recon.parser_message


def test_corrupted_candidate_fails_real_parser(tmp_path):
    """Corrupted binary bytes fail real parser validation and record failure reason."""
    bad_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 30 + b"corrupt stream"
    ev_path = tmp_path / "bad_ev.raw"
    with open(ev_path, "wb") as f:
        f.write(bad_bytes)

    frag = Fragment(
        id="frag_bad",
        offset=0,
        length=len(bad_bytes),
        type_hint="jpeg",
        source=str(ev_path),
    )
    cluster = FragmentCluster(cluster_id="c_bad", inferred_type="jpeg")

    recon = reconstruct_structured_file(cluster, [frag], output_dir=tmp_path)
    assert recon.status == "validation_failed"
    assert recon.structural_validity == 0.0
    assert "failed" in recon.parser_message.lower()


def test_evidence_remains_read_only_and_unchanged(temp_evidence, tmp_path):
    """Original evidence bytes and SHA-256 hash are strictly unchanged after reconstruction."""
    f1 = temp_evidence["frag1"]
    f2 = temp_evidence["frag2"]
    cluster = FragmentCluster(cluster_id="c_ro", inferred_type="jpeg")

    reconstruct_structured_file(cluster, [f1, f2], output_dir=tmp_path)

    with open(temp_evidence["path"], "rb") as f:
        sha_after = hashlib.sha256(f.read()).hexdigest()

    assert sha_after == temp_evidence["sha256"]


def test_gap_information_calculation():
    """Verify gap information computation between non-contiguous fragments."""
    f1 = Fragment(id="F1", offset=100, length=50)
    f2 = Fragment(id="F2", offset=200, length=50)
    f3 = Fragment(id="F3", offset=250, length=50)  # Contiguous with f2

    gap_info = compute_gap_information([f1, f2, f3])
    assert gap_info["has_gaps"] is True
    assert gap_info["gap_count"] == 1
    assert gap_info["total_gap_bytes"] == 50
    assert gap_info["gaps"][0]["prev_fragment_id"] == "F1"
    assert gap_info["gaps"][0]["next_fragment_id"] == "F2"
    assert gap_info["gaps"][0]["gap_start"] == 150
    assert gap_info["gaps"][0]["gap_length"] == 50


def test_text_reconstruction_small_cluster(tmp_path):
    """Small text cluster orders fragments by continuity and sentence boundaries."""
    ev_path = tmp_path / "text_ev.raw"
    p1 = b"The quick brown fox "
    p2 = b"jumps over the lazy dog. "
    p3 = b"Digital forensics evidence intact."

    with open(ev_path, "wb") as f:
        f.write(p1 + p2 + p3)

    f1 = Fragment(id="T1", offset=0, length=len(p1), source=str(ev_path), type_hint="text")
    f2 = Fragment(id="T2", offset=len(p1), length=len(p2), source=str(ev_path), type_hint="text")
    f3 = Fragment(id="T3", offset=len(p1) + len(p2), length=len(p3), source=str(ev_path), type_hint="text")

    cluster = FragmentCluster(cluster_id="c_txt", inferred_type="text")
    recon = reconstruct_small_text_cluster(cluster, [f3, f1, f2], output_dir=tmp_path)

    assert recon.status in ("reconstructed", "ambiguous")
    assert (tmp_path / "recon_c_txt.txt").exists()
    assert recon.structural_validity == 1.0


def test_invalid_llm_fragment_ids_rejected(tmp_path):
    """Reconstruct large text cluster rejects hallucinated LLM IDs (e.g. F99) and falls back to offset."""
    ev_path = tmp_path / "large_txt.raw"
    with open(ev_path, "wb") as f:
        f.write(b"ABCDEFGHIJ" * 20)

    fragments = [
        Fragment(id=f"F0{i}", offset=i * 20, length=20, source=str(ev_path), type_hint="text")
        for i in range(1, 8)
    ]
    cluster = FragmentCluster(cluster_id="c_large_txt", inferred_type="text")

    # LLM hallucinates F99
    fake_llm = lambda prompt_frags: ["F03", "F01", "F99", "F02"]

    recon = reconstruct_large_text_cluster(cluster, fragments, output_dir=tmp_path, llm_callable=fake_llm)

    # Must reject LLM and fall back to offset order
    assert recon.status == "reconstructed"
    assert "LLM proposal rejected" in recon.parser_message
    assert "F99" not in recon.fragment_ids
    assert recon.fragment_ids == [f"F0{i}" for i in range(1, 8)]


def test_cluster_only_status_on_empty_fragments(tmp_path):
    """Empty cluster produces cluster_only status without crashing."""
    cluster = FragmentCluster(cluster_id="c_empty", inferred_type="jpeg")
    recon = reconstruct_structured_file(cluster, [], output_dir=tmp_path)
    assert recon.status == "cluster_only"
    assert recon.structural_validity == 0.0


def test_run_stage_5_pipeline(tmp_path):
    """run_stage_5 executes through Stage 1-4 and produces ReconstructedFile objects."""
    img = Image.new("RGB", (20, 20), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()

    ev_path = tmp_path / "full_ev.raw"
    with open(ev_path, "wb") as f:
        f.write(b"\x00" * 128 + jpeg_bytes + b"\x00" * 128)

    evidence, fragments, features, graph, clusters, orphans, reconstructed = run_stage_5(str(ev_path))

    assert evidence is not None
    assert len(fragments) > 0
    assert len(features) == len(fragments)
    assert isinstance(clusters, list)
    assert isinstance(orphans, list)
    assert isinstance(reconstructed, list)
    for rf in reconstructed:
        assert isinstance(rf, ReconstructedFile)
        assert rf.status in ("reconstructed", "validation_failed", "ambiguous", "cluster_only")


def test_ground_truth_never_accessed_stage5():
    """Verify ground_truth.json is never read or imported by Stage 5 code."""
    import inspect
    import recovery.reconstruction as rmod
    import recovery.validation as vmod
    import recovery.text_reconstruction as tmod

    for mod in (rmod, vmod, tmod):
        source = inspect.getsource(mod)
        assert "ground_truth" not in source.lower()


def test_ambiguous_candidates_marked_ambiguous(tmp_path):
    """When candidates have symmetric/tied continuity, ambiguous=True is explicitly set."""
    ev_path = tmp_path / "tied_text.raw"
    # Identical symmetric snippets with matching punctuation and identical length
    s1 = b"Alpha block data. "
    s2 = b"Bravo block data. "
    with open(ev_path, "wb") as f:
        f.write(s1 + s2)

    # Offset ordering gives +1 bonus normally; create tied fragments where orderings score identically
    f1 = Fragment(id="TA", offset=0, length=len(s1), source=str(ev_path), type_hint="text")
    f2 = Fragment(id="TB", offset=0, length=len(s2), source=str(ev_path), type_hint="text")

    cluster = FragmentCluster(cluster_id="c_ambig", inferred_type="text")
    recon = reconstruct_small_text_cluster(cluster, [f1, f2], output_dir=tmp_path)

    # Both TA->TB and TB->TA score identically (end with dot, start with uppercase, offset same)
    assert recon.ambiguous is True
    assert recon.status == "ambiguous"
    assert "Ambiguous candidate" in recon.parser_message


def test_deterministic_reconstruction_bytes(temp_evidence, tmp_path):
    """Repeated runs of reconstruction produce bit-for-bit identical outputs and file hashes."""
    f1 = temp_evidence["frag1"]
    f2 = temp_evidence["frag2"]
    cluster = FragmentCluster(cluster_id="c_det2", inferred_type="jpeg")

    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"

    recon1 = reconstruct_structured_file(cluster, [f2, f1], output_dir=dir1)
    recon2 = reconstruct_structured_file(cluster, [f1, f2], output_dir=dir2)

    with open(dir1 / "recon_c_det2.jpg", "rb") as fa:
        bytes1 = fa.read()
    with open(dir2 / "recon_c_det2.jpg", "rb") as fb:
        bytes2 = fb.read()

    assert bytes1 == bytes2
    assert recon1.gap_information == recon2.gap_information
    assert recon1.structural_validity == recon2.structural_validity
    assert recon1.status == recon2.status

