import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import streamlit as st

from models.pipeline_result import PipelineResult
from models.reconstructed_file import ReconstructedFile
from .signal_charts import render_integrity_signals
from .file_preview import render_file_preview


def render_analyst_workspace(result: Optional[PipelineResult] = None) -> None:
    """
    Render consolidated Analyst Workspace allowing investigator to evaluate complete
    recovery and triage outcomes in one single unified pane.
    """
    st.header("Forensic Analyst Workspace")
    st.caption("Consolidated operational dashboard for end-to-end evidence reconstruction, priority triage, and artifact inspection.")

    if not result:
        st.info("No active recovery analysis loaded. Select an evidence image and click 'RUN FULL RECOVERY ANALYSIS'.")
        return

    # ============================================================
    # SECTION 1: Evidence Identity & Pipeline Run Status
    # ============================================================
    st.subheader("1. Evidence Identity & Run Status")
    col1, col2, col3, col4 = st.columns(4)

    ev_size = result.evidence.metadata.get("size_bytes", 0) if result.evidence else 0
    col1.metric("Evidence Size", f"{ev_size:,} B")
    col2.metric("Processing Time", f"{result.total_duration:.2f} s")
    col3.metric("Status", "⚡ Cached Run" if result.cached else "✅ Pipeline Complete")
    col4.metric("Completed At (UTC)", result.completed_at[:19].replace("T", " "))

    st.text_input("Evidence SHA-256 Cryptographic Digest", value=result.evidence_sha256, disabled=True)
    st.caption(f"Source Evidence Image: `{result.evidence_path}` | Pipeline Version: `v{result.pipeline_version}`")

    st.markdown("---")

    # ============================================================
    # SECTION 2: Recovery Statistics
    # ============================================================
    st.subheader("2. Recovery Statistics")
    m1, m2, m3, m4, m5, m6 = st.columns(6)

    total_frags = len(result.fragments)
    total_clusters = len(result.clusters)
    total_cands = len(result.reconstructed_files)
    struct_valid = sum(1 for r in result.reconstructed_files if (r.structural_validity or 0.0) >= 1.0)
    sensitive_cands = sum(1 for r in result.reconstructed_files if (r.sensitivity_level or "NONE") != "NONE")
    avg_recov = (
        sum(r.observed_recovery_ratio for r in result.reconstructed_files) / max(1, total_cands)
    )

    m1.metric("Fragments Carved", total_frags)
    m2.metric("Clusters Formed", total_clusters)
    m3.metric("Reconstruction Cands", total_cands)
    m4.metric("Structurally Valid", struct_valid)
    m5.metric("Sensitive Candidates", sensitive_cands)
    m6.metric("Avg Observed Recovery", f"{avg_recov * 100:.1f}%")

    st.markdown("---")

    # ============================================================
    # SECTION 3: Recovered File Cards
    # ============================================================
    st.subheader("3. Recovered File Cards")
    if not result.reconstructed_files:
        st.info("No file candidates reconstructed from current evidence.")
    else:
        # Display up to 4 file cards side-by-side or in rows
        card_cols = st.columns(min(3, max(1, len(result.reconstructed_files))))
        for idx, cand in enumerate(result.reconstructed_files):
            col_idx = idx % len(card_cols)
            with card_cols[col_idx]:
                with st.container(border=True):
                    cand_id = cand.candidate_id or cand.id
                    st.markdown(f"#### Rank {idx + 1}: `{cand_id}`")
                    st.caption(f"Format: **{cand_id.split('.')[-1].upper() if '.' in cand_id else cand.file_type.upper()}** | Status: `{cand.recovery_status}`")
                    st.markdown(f"**Observed Recovery:** `{cand.observed_recovery_ratio * 100:.1f}%`")
                    st.markdown(f"**Recovered Bytes:** `{cand.recovered_bytes:,}` B")
                    st.markdown(f"**Priority Score:** `{cand.priority_score:.4f}` ({cand.sensitivity_level})")

                    if cand.output_path and os.path.exists(cand.output_path):
                        with open(cand.output_path, "rb") as af:
                            file_bytes = af.read()
                        st.download_button(
                            label=f"⬇️ Download ({Path(cand.output_path).name})",
                            data=file_bytes,
                            file_name=Path(cand.output_path).name,
                            mime="application/octet-stream",
                            key=f"card_dl_{cand_id}",
                            use_container_width=True,
                        )

    st.markdown("---")

    # ============================================================
    # SECTION 4: Priority-Ranked Candidates Table
    # ============================================================
    st.subheader("4. Priority-Ranked Candidates")
    if result.reconstructed_files:
        triage_rows = [
            {
                "Rank": idx + 1,
                "Candidate ID": r.candidate_id or r.id,
                "File Type": r.file_type.upper(),
                "Status": r.recovery_status or r.status,
                "Observed Recovery Ratio": f"{r.observed_recovery_ratio * 100:.1f}%",
                "Integrity Score": f"{r.composite_integrity_score * 100:.1f}%",
                "Sensitivity": r.sensitivity_level or "NONE",
                "Priority Score": f"{r.priority_score:.4f}",
                "Factual Priority Reason": r.priority_reason or "—",
            }
            for idx, r in enumerate(result.reconstructed_files)
        ]
        st.dataframe(triage_rows, use_container_width=True)

    st.markdown("---")

    # ============================================================
    # SECTION 5: Sensitivity Findings
    # ============================================================
    st.subheader("5. Sensitivity Classification Findings")
    sensitive_cands_list = [r for r in result.reconstructed_files if (r.sensitivity_level or "NONE") != "NONE"]
    if not sensitive_cands_list:
        st.success("No sensitive identifier patterns or restricted keywords detected in reconstructed artifacts.")
    else:
        sens_rows = [
            {
                "Candidate ID": r.candidate_id or r.id,
                "Sensitivity Level": r.sensitivity_level,
                "Detected Categories": ", ".join(r.detected_categories) if r.detected_categories else "None",
                "Pattern Matches": len(r.sensitivity_matches) if r.sensitivity_matches else 0,
                "Priority Score": f"{r.priority_score:.4f}",
            }
            for r in sensitive_cands_list
        ]
        st.dataframe(sens_rows, use_container_width=True)

    st.markdown("---")

    # ============================================================
    # SECTION 6: Integrity Breakdown
    # ============================================================
    st.subheader("6. Decomposed Integrity Breakdown")
    if result.reconstructed_files:
        inspect_cand_id = st.selectbox(
            "Select Candidate to Inspect Decomposed Signals",
            options=[r.candidate_id or r.id for r in result.reconstructed_files],
            key="workspace_signal_inspect",
        )
        selected_cand = next((r for r in result.reconstructed_files if (r.candidate_id or r.id) == inspect_cand_id), None)
        if selected_cand:
            render_integrity_signals(selected_cand)

    st.markdown("---")

    # ============================================================
    # SECTION 7: Technical Limitations
    # ============================================================
    st.subheader("7. Technical Limitations & Non-Assertion Notice")
    st.info(
        "ℹ️ **Forensic Limitations & Methodology Disclaimer**:\n\n"
        "1. **Observed Recovery Ratio**: Reflects surviving candidate fragment bytes relative to the observed candidate span; "
        "it is not the recovery percentage of an unknown original file.\n"
        "2. **Sensitivity Classifications**: Detections reflect regex and keyword pattern matches. They indicate potential sensitive "
        "identifiers and do not assert verified personal identity or live validity.\n"
        "3. **Investigative Priority**: Intended purely as an objective triage ordering filter for investigators, not an absolute truth claim.\n"
        "4. **Evidence Preservation**: All source evidence images remain strictly read-only and cryptographically verified via SHA-256."
    )
