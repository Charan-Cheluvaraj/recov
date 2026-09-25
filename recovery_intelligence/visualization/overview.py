import os
import streamlit as st
from typing import Optional, Union, Dict, Any, List
from models.ranked_results import RankedResults
from models.pipeline_result import PipelineResult


def render_overview(results: Optional[Union[PipelineResult, RankedResults]] = None) -> None:
    """Render high-level executive summary metrics, stage timing breakdown, and dataset overview."""
    st.header("Executive Summary & Overview")

    if not results:
        st.info("No active pipeline results loaded. Select an evidence image and click 'RUN FULL RECOVERY ANALYSIS'.")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Fragments Carved", 0)
        m2.metric("Reconstructed Files", 0)
        m3.metric("Artifacts Recovered", 0)
        m4.metric("Average Recovery Ratio", "0.0%")
        return

    # Check if results is PipelineResult or legacy RankedResults
    is_full_result = isinstance(results, PipelineResult)

    # 1. Pipeline Status & Evidence Metadata
    st.subheader("Pipeline Execution Status")
    s1, s2, s3, s4 = st.columns(4)

    ev_hash = results.evidence_sha256 if is_full_result else (results.evidence_image_hash or "N/A")
    ev_size = (
        results.evidence.metadata.get("size_bytes", 0)
        if (is_full_result and results.evidence)
        else 0
    )
    total_time = results.total_duration if is_full_result else 0.0
    status_label = ("⚡ Loaded Cached Analysis" if (is_full_result and results.cached) else "✅ Pipeline Complete")

    s1.metric("Status", status_label)
    s2.metric("Total Duration", f"{total_time:.2f} s")
    s3.metric("Evidence Size", f"{ev_size:,} B" if ev_size else "—")
    s4.metric("Evidence Hash", ev_hash[:12] + "..." if len(ev_hash) > 12 else ev_hash)

    st.text_input("Evidence SHA-256 Digest", value=ev_hash, disabled=True)

    st.markdown("---")

    # 2. Comprehensive Pipeline Metrics
    st.subheader("Recovery Pipeline Metrics")
    c1, c2, c3, c4 = st.columns(4)

    if is_full_result:
        frags_carved = len(results.fragments)
        frags_char = len(results.characterized_fragments)
        feat_vecs = len(results.feature_vectors)
        rel_edges = len(results.relationship_graph.get("edges", []))
        clusters_count = len(results.clusters)
        orphans_count = len(results.orphans)
        recon_cands = len(results.reconstructed_files)
        val_cands = sum(1 for r in results.reconstructed_files if r.is_successfully_recovered or r.recovery_state in ("FULL_RECOVERY", "VALIDATED_RECOVERY"))
        partial_cands = sum(1 for r in results.reconstructed_files if r.recovery_state == "PARTIAL_RECONSTRUCTION")
        raw_cands = sum(1 for r in results.reconstructed_files if r.recovery_state == "RAW_BINARY_RECOVERY")
        invalid_cands = sum(1 for r in results.reconstructed_files if r.recovery_state in ("INVALID_RECONSTRUCTION", "UNRECOVERABLE"))
        recov_artifacts = sum(1 for r in results.reconstructed_files if r.output_path and os.path.exists(r.output_path))
        avg_recov_ratio = (
            sum(r.observed_recovery_ratio for r in results.reconstructed_files) / max(1, recon_cands)
        )
        sensitive_cands = sum(1 for r in results.reconstructed_files if (r.sensitivity_level or "NONE") != "NONE")
        high_pri_cands = sum(1 for r in results.reconstructed_files if (r.priority_score or 0.0) >= 0.70)
    else:
        frags_carved = len(results.orphans)
        frags_char = frags_carved
        feat_vecs = 0
        rel_edges = 0
        clusters_count = len(results.clusters)
        orphans_count = len(results.orphans)
        recon_cands = len(results.files)
        val_cands = sum(1 for r in results.files if (r.structural_validity or 0.0) >= 1.0)
        partial_cands = sum(1 for r in results.files if r.recovery_state == "PARTIAL_RECONSTRUCTION")
        raw_cands = sum(1 for r in results.files if r.recovery_state == "RAW_BINARY_RECOVERY")
        invalid_cands = sum(1 for r in results.files if (r.structural_validity or 0.0) < 1.0)
        recov_artifacts = sum(1 for r in results.files if r.output_path and os.path.exists(r.output_path))
        avg_recov_ratio = (
            sum(r.observed_recovery_ratio for r in results.files) / max(1, recon_cands)
        )
        sensitive_cands = sum(1 for r in results.files if (r.sensitivity_level or "NONE") != "NONE")
        high_pri_cands = sum(1 for r in results.files if (r.priority_score or 0.0) >= 0.70)

    c1.metric("Fragments Carved", frags_carved)
    c2.metric("Characterized Fragments", frags_char)
    c3.metric("Feature Vectors (64D)", feat_vecs)
    c4.metric("Relationship Edges", rel_edges)

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Clusters Formed", clusters_count)
    c6.metric("Orphan Fragments", orphans_count)
    c7.metric("Reconstruction Cands", recon_cands)
    c8.metric("Validated Recoveries", val_cands)

    c9, c10, c11, c12 = st.columns(4)
    c9.metric("Partial Candidates", partial_cands)
    c10.metric("Raw Binary Salvage", raw_cands)
    c11.metric("Invalid Reconstructions", invalid_cands)
    c12.metric("Avg Observed Ratio", f"{avg_recov_ratio * 100:.1f}%")

    st.markdown("---")

    # 3. Stage Timing & Performance Table
    if is_full_result and results.stage_durations:
        st.subheader("Stage Performance Breakdown")
        stage_names = [
            ("Stage 1: Evidence Ingestion & Carving", "stage_1_duration", frags_carved),
            ("Stage 2: Entropy Characterization", "stage_2_duration", frags_char),
            ("Stage 3: Fragment Fingerprinting", "stage_3_duration", feat_vecs),
            ("Stage 4: Relationships & Clustering", "stage_4_duration", f"{clusters_count} clusters / {orphans_count} orphans"),
            ("Stage 5: Candidate Reconstruction", "stage_5_duration", recon_cands),
            ("Stage 6: Integrity Scoring", "stage_6_duration", recon_cands),
            ("Stage 7: Recoverability Assessment", "stage_7_duration", f"{recov_artifacts} artifacts"),
            ("Stage 8: Sensitivity & Priority", "stage_8_duration", f"{recon_cands} ranked"),
        ]

        perf_rows = []
        for name, dur_key, count in stage_names:
            dur = results.stage_durations.get(dur_key, 0.0)
            pct = (dur / max(0.001, total_time)) * 100.0 if total_time > 0 else 0.0
            perf_rows.append({
                "Pipeline Stage": name,
                "Duration (Seconds)": f"{dur:.4f} s",
                "Share of Total Time": f"{pct:.1f}%",
                "Output Count": str(count),
            })

        st.dataframe(perf_rows, use_container_width=True)

    # 4. Factual Text Summary
    if is_full_result and results.final_summary:
        with st.expander("📄 View Factual Forensic Summary Log", expanded=False):
            st.code(results.final_summary, language="text")
