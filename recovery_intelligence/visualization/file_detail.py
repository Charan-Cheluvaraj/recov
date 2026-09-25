import os
from pathlib import Path
from typing import Optional
import streamlit as st
from models.reconstructed_file import ReconstructedFile
from .file_preview import render_file_preview
from .signal_charts import render_integrity_signals


def render_file_detail(file: Optional[ReconstructedFile] = None, evidence_sha256: str = "") -> None:
    """Render comprehensive forensic evidence chain and deep-dive inspection for a candidate."""
    st.header("Forensic File Detail & Evidence Chain")
    if not file:
        st.info("Select a candidate file from Ranked Results or Recovered Files to inspect its forensic evidence chain.")
        return

    cand_id = file.candidate_id or file.id
    st.subheader(f"Candidate: `{cand_id}` ({file.file_type.upper()})")

    # Forensic Chain Summary
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recovery State", file.recovery_state or file.recovery_status)
    c2.metric("Observed Ratio", f"{file.observed_recovery_ratio * 100:.1f}%")
    c3.metric("Unique Rec. Bytes", f"{file.unique_recovered_bytes or file.recovered_bytes:,} B")
    c4.metric("Parser Validity", "VALID" if file.structural_validity >= 1.0 else "FAILED")

    st.markdown("---")

    col_meta, col_prev = st.columns([1, 1])

    with col_meta:
        st.markdown("### Evidence Chain & Lineage")
        st.markdown(f"- **Source Evidence SHA-256:** `{evidence_sha256 or 'N/A'}`")
        st.markdown(f"- **Candidate ID:** `{cand_id}`")
        st.markdown(f"- **Associated Cluster:** `{file.cluster_id}`")
        st.markdown(f"- **Associated Fragment IDs ({len(file.fragment_ids)}):** `{', '.join(file.fragment_ids) if file.fragment_ids else 'None'}`")
        st.markdown(f"- **Source Offsets:** `{file.source_offsets or 'None'}`")
        st.markdown(f"- **Disjoint Source Ranges:** `{file.source_ranges or 'None'}`")
        st.markdown(f"- **File Type:** `{file.file_type.upper()}`")
        st.markdown(f"- **Recovery State:** `{file.recovery_state or file.recovery_status}`")
        st.markdown(f"- **Unique Recovered Bytes:** `{file.unique_recovered_bytes or file.recovered_bytes:,}` B")
        st.markdown(f"- **Overlap / Duplicate Bytes:** `{file.overlap_bytes:,}` B")
        st.markdown(f"- **Missing Gap Bytes:** `{file.missing_or_unknown_bytes:,}` B")
        st.markdown(f"- **Observed Candidate Span:** `{file.observed_candidate_span:,}` B")
        st.markdown(f"- **Observed Recovery Ratio:** `{file.observed_recovery_ratio * 100:.2f}%`")

        if file.logical_recovery_ratio_available and file.logical_recovery_ratio is not None:
            st.markdown(f"- **Logical File Recovery:** `{file.logical_recovery_ratio * 100:.2f}%` (Known Size: {file.known_original_size:,} B)")
        else:
            st.markdown("- **Logical File Recovery:** `Unavailable` *(requires filesystem metadata)*")

        st.markdown(f"- **Parser Validation Status:** `{file.parser_validation_status}`")
        st.markdown(f"- **Parser Diagnostic:** {file.parser_message or 'No parser message'}")
        st.markdown(f"- **Artifact SHA-256:** `{file.output_sha256 or file.artifact_sha256 or 'N/A'}`")
        st.markdown(f"- **Artifact Path:** `{file.output_path or file.artifact_path or 'Not saved to disk'}`")
        st.markdown(f"- **Investigative Priority:** `{file.priority_score:.4f}`")
        st.markdown(f"- **Sensitivity Level:** `{file.sensitivity_level}`")
        st.markdown(f"- **Recovery Reasoning:** {file.recovery_reason or 'No reasoning recorded'}")

        if file.output_path and os.path.exists(file.output_path):
            with open(file.output_path, "rb") as af:
                file_bytes = af.read()
            cand_name = Path(file.output_path).name
            st.download_button(
                label=f"⬇️ Download Candidate Artifact ({cand_name})",
                data=file_bytes,
                file_name=cand_name,
                mime="application/octet-stream",
                key=f"detail_dl_{cand_id}",
                type="primary",
                use_container_width=True,
            )

    with col_prev:
        render_file_preview(file.output_path or file.artifact_path, file_type=file.file_type)

    st.markdown("---")
    st.subheader("Integrity Signals Breakdown")
    render_integrity_signals(file)

