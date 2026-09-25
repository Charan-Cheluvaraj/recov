import os
import json
import pytest
from pathlib import Path

from config import settings
from models.pipeline_result import PipelineResult
from pipeline.orchestrator import run_full_pipeline, generate_factual_pipeline_summary
from storage.cache import (
    load_pipeline_cache,
    save_pipeline_cache,
    invalidate_pipeline_cache,
    get_pipeline_cache_path,
)
from visualization.file_preview import render_hex_preview


@pytest.fixture
def sample_evidence(tmp_path):
    """Create a deterministic synthetic evidence file with JPEG and text headers."""
    ev_file = tmp_path / "test_evidence.raw"
    # Construct synthetic evidence containing a valid minimal JPEG and a text segment
    jpeg_header = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
    jpeg_body = b"A" * 1024
    jpeg_footer = b"\xFF\xD9"
    text_data = b"CONFIDENTIAL INVESTIGATION REPORT: Subject Aadhaar: 2345 6789 0123. Contact: agent@agency.gov."
    
    content = (
        b"\x00" * 512
        + jpeg_header
        + jpeg_body
        + jpeg_footer
        + b"\x00" * 512
        + text_data
        + b"\x00" * 512
    )
    ev_file.write_bytes(content)
    return str(ev_file)


@pytest.fixture
def empty_evidence(tmp_path):
    """Create an empty / zero-byte evidence file with no magic-byte headers."""
    ev_file = tmp_path / "empty_evidence.raw"
    ev_file.write_bytes(b"\x00" * 2048)
    return str(ev_file)


def test_full_pipeline_sequence_and_stage_durations(sample_evidence):
    """Verify that run_full_pipeline executes Stages 1-8 sequentially and records positive stage durations."""
    result = run_full_pipeline(sample_evidence, force_rerun=True)

    assert isinstance(result, PipelineResult)
    assert result.cached is False
    assert result.pipeline_version == settings.PIPELINE_VERSION
    assert len(result.evidence_sha256) == 64
    assert result.total_duration > 0.0

    # Verify per-stage timings are recorded
    for stage_num in range(1, 9):
        dur_key = f"stage_{stage_num}_duration"
        assert dur_key in result.stage_durations
        assert result.stage_durations[dur_key] >= 0.0

    assert sum(result.stage_durations.values()) == pytest.approx(result.total_duration, rel=1e-3)

    # Verify all Stage 1-8 outputs exist
    assert result.evidence is not None
    assert result.evidence.sha256 == result.evidence_sha256
    assert isinstance(result.fragments, list)
    assert isinstance(result.characterized_fragments, list)
    assert isinstance(result.feature_vectors, list)
    assert isinstance(result.relationship_graph, dict)
    assert isinstance(result.clusters, list)
    assert isinstance(result.orphans, list)
    assert isinstance(result.reconstructed_files, list)
    assert isinstance(result.recoverability_results, list)
    assert isinstance(result.sensitivity_results, list)
    assert result.ranked_results is not None
    assert isinstance(result.final_summary, str)
    assert "DIGITAL EVIDENCE RECONSTRUCTION & RECOVERY SUMMARY" in result.final_summary


def test_caching_and_instant_retrieval(sample_evidence):
    """Verify that a second run on identical evidence loads instantly from cache with cached=True."""
    # Run 1: Cold run
    result1 = run_full_pipeline(sample_evidence, force_rerun=True)
    assert result1.cached is False

    # Run 2: Cached run
    result2 = run_full_pipeline(sample_evidence, force_rerun=False)
    assert result2.cached is True
    assert result2.evidence_sha256 == result1.evidence_sha256
    assert len(result2.reconstructed_files) == len(result1.reconstructed_files)
    assert len(result2.clusters) == len(result1.clusters)
    assert len(result2.fragments) == len(result1.fragments)


def test_force_rerun_invalidates_cache(sample_evidence):
    """Verify that force_rerun=True bypasses and refreshes the cache."""
    result1 = run_full_pipeline(sample_evidence, force_rerun=False)
    result2 = run_full_pipeline(sample_evidence, force_rerun=True)
    assert result2.cached is False
    assert result2.evidence_sha256 == result1.evidence_sha256


def test_changed_evidence_creates_different_cache_entries(tmp_path):
    """Verify that different evidence files produce different hashes and cache entries."""
    ev1 = tmp_path / "ev1.raw"
    ev1.write_bytes(b"\xFF\xD8\xFF\xE0" + b"ImageA" * 100 + b"\xFF\xD9")
    ev2 = tmp_path / "ev2.raw"
    ev2.write_bytes(b"\xFF\xD8\xFF\xE0" + b"ImageB" * 100 + b"\xFF\xD9")

    res1 = run_full_pipeline(str(ev1), force_rerun=True)
    res2 = run_full_pipeline(str(ev2), force_rerun=True)

    assert res1.evidence_sha256 != res2.evidence_sha256
    p1 = get_pipeline_cache_path(res1.evidence_sha256, settings.PIPELINE_VERSION)
    p2 = get_pipeline_cache_path(res2.evidence_sha256, settings.PIPELINE_VERSION)
    assert p1 != p2
    assert p1.exists()
    assert p2.exists()


def test_corrupted_cache_file_is_safely_rejected(sample_evidence):
    """Verify that an invalid/corrupted cache JSON is discarded and recomputed safely."""
    res = run_full_pipeline(sample_evidence, force_rerun=False)
    cache_path = get_pipeline_cache_path(res.evidence_sha256, settings.PIPELINE_VERSION)
    assert cache_path.exists()

    # Corrupt the cache file
    cache_path.write_text("{invalid json truncated", encoding="utf-8")

    # Load cache directly should return None
    loaded = load_pipeline_cache(res.evidence_sha256, settings.PIPELINE_VERSION)
    assert loaded is None

    # Pipeline should recover gracefully and recompute
    new_res = run_full_pipeline(sample_evidence, force_rerun=False)
    assert new_res is not None
    assert new_res.evidence_sha256 == res.evidence_sha256
    assert cache_path.exists()


def test_empty_evidence_stages_do_not_crash(empty_evidence):
    """Verify that the pipeline does not crash on evidence yielding 0 carved fragments."""
    result = run_full_pipeline(empty_evidence, force_rerun=True)

    assert result is not None
    assert len(result.fragments) == 0
    assert len(result.characterized_fragments) == 0
    assert len(result.feature_vectors) == 0
    assert len(result.clusters) == 0
    assert len(result.reconstructed_files) == 0
    assert "No reconstruction candidates produced" in result.final_summary


def test_hex_preview_formatting():
    """Verify that render_hex_preview handles empty bytes and regular bytes safely."""
    assert render_hex_preview(b"") == "Empty data stream (0 bytes)."
    preview = render_hex_preview(b"HELLO WORLD FORENSICS")
    assert "48 45 4C 4C 4F" in preview
    assert "HELLO WORLD" in preview


def test_factual_summary_consistency(sample_evidence):
    """Verify that the final summary accurately reflects actual values without fabrication."""
    result = run_full_pipeline(sample_evidence, force_rerun=False)
    summary = result.final_summary

    assert result.evidence_sha256 in summary
    assert str(len(result.fragments)) in summary
    assert str(len(result.clusters)) in summary
    assert str(len(result.reconstructed_files)) in summary


def test_recovered_artifacts_written_to_disk(sample_evidence):
    """Verify that any reconstructed candidates have their recovered artifacts accessible on disk."""
    result = run_full_pipeline(sample_evidence, force_rerun=False)
    for recon in result.reconstructed_files:
        if recon.output_path:
            out_file = Path(recon.output_path)
            assert out_file.exists()
            assert out_file.stat().st_size > 0
            assert recon.output_sha256 is not None
            assert len(recon.output_sha256) == 64
