import os
from pathlib import Path
from typing import List, Optional
import streamlit as st

from models.reconstructed_file import ReconstructedFile
from .file_preview import render_file_preview


def render_recovered_files_view(reconstructed_list: Optional[List[ReconstructedFile]] = None) -> None:
    """Render dedicated Recovered Files view with interactive tables, inspection, and multi-format preview."""
    st.header("Recovered Files & Artifact Inspection")
    st.caption("Inspect and download digital evidence artifacts separated strictly into validated recoveries, partial candidates, raw binary salvage, and invalid reconstructions.")

    if not reconstructed_list:
        st.info("No recovered file artifacts available. Select an evidence image and click 'RUN FULL RECOVERY ANALYSIS'.")
        return

    # 1. High-Level Categorized Summary Metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    
    validated_cands = [r for r in reconstructed_list if r.is_successfully_recovered or r.recovery_state in ("FULL_RECOVERY", "VALIDATED_RECOVERY")]
    partial_cands = [r for r in reconstructed_list if r.recovery_state == "PARTIAL_RECONSTRUCTION"]
    invalid_cands = [r for r in reconstructed_list if r.recovery_state in ("INVALID_RECONSTRUCTION", "UNRECOVERABLE")]
    raw_cands = [r for r in reconstructed_list if r.recovery_state == "RAW_BINARY_RECOVERY"]

    avg_ratio = (
        sum(r.observed_recovery_ratio for r in reconstructed_list) / max(1, len(reconstructed_list))
    )

    c1.metric("Validated Recoveries", len(validated_cands))
    c2.metric("Partial Candidates", len(partial_cands))
    c3.metric("Raw Binary Salvage", len(raw_cands))
    c4.metric("Invalid Reconstructions", len(invalid_cands))
    c5.metric("Avg Observed Ratio", f"{avg_ratio * 100:.1f}%")

    st.markdown("---")

    # 2. Categorized Tabs
    tab_all, tab_val, tab_part, tab_raw, tab_inv = st.tabs([
        f"All Candidates ({len(reconstructed_list)})",
        f"Validated Recoveries ({len(validated_cands)})",
        f"Partial Candidates ({len(partial_cands)})",
        f"Raw Binary Salvage ({len(raw_cands)})",
        f"Invalid Reconstructions ({len(invalid_cands)})",
    ])

    def _build_table(cands: List[ReconstructedFile]):
        if not cands:
            st.info("No candidates in this category.")
            return
        table_rows = [
            {
                "Candidate ID": r.candidate_id or r.id,
                "File Type": r.file_type.upper(),
                "Recovery State": r.recovery_state or r.recovery_status,
                "Unique Rec. Bytes": f"{r.unique_recovered_bytes or r.recovered_bytes:,} B",
                "Missing/Gaps": f"{r.missing_or_unknown_bytes:,} B",
                "Observed Recovery Ratio": f"{r.observed_recovery_ratio * 100:.1f}%",
                "Parser Validity": "VALID" if r.structural_validity >= 1.0 else "FAILED",
                "Integrity": f"{r.composite_integrity_score * 100:.1f}%",
                "Priority": f"{r.priority_score:.4f}" if r.priority_score is not None else "0.0000",
                "Output SHA-256": r.output_sha256[:16] + "..." if r.output_sha256 else "—",
            }
            for r in cands
        ]
        st.dataframe(table_rows, use_container_width=True)

    with tab_all:
        _build_table(reconstructed_list)
    with tab_val:
        _build_table(validated_cands)
    with tab_part:
        _build_table(partial_cands)
    with tab_raw:
        _build_table(raw_cands)
    with tab_inv:
        _build_table(invalid_cands)

    st.markdown("---")

    # 3. Candidate Inspector, Preview, and Download
    st.subheader("Candidate Artifact Inspector")
    cand_options = [r.candidate_id or r.id for r in reconstructed_list]
    selected_id = st.selectbox("Select Candidate to Inspect & Preview", options=cand_options)
    selected_recon = next((r for r in reconstructed_list if (r.candidate_id or r.id) == selected_id), None)

    if selected_recon:
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown("##### Forensic Candidate Metadata")
            st.markdown(f"**Candidate ID:** `{selected_recon.candidate_id or selected_recon.id}`")
            st.markdown(f"**Associated Cluster:** `{selected_recon.cluster_id}`")
            st.markdown(f"**File Format:** `{selected_recon.file_type.upper()}`")
            st.markdown(f"**Recovery State:** `{selected_recon.recovery_state or selected_recon.recovery_status}`")
            st.markdown(f"**Observed Recovery Ratio:** `{selected_recon.observed_recovery_ratio * 100:.2f}%` ({selected_recon.observed_recovery_ratio:.4f})")
            
            if selected_recon.logical_recovery_ratio_available and selected_recon.logical_recovery_ratio is not None:
                st.markdown(f"**Logical File Recovery:** `{selected_recon.logical_recovery_ratio * 100:.2f}%` (Known Size: {selected_recon.known_original_size:,} B)")
            else:
                st.markdown("**Logical File Recovery:** `Unavailable` *(requires filesystem metadata)*")

            st.markdown(f"**Unique Recovered Bytes:** `{selected_recon.unique_recovered_bytes or selected_recon.recovered_bytes:,}` B")
            st.markdown(f"**Overlap/Duplicate Bytes:** `{selected_recon.overlap_bytes:,}` B")
            st.markdown(f"**Missing/Unknown Gap Bytes:** `{selected_recon.missing_or_unknown_bytes:,}` B")
            st.markdown(f"**Observed Candidate Span:** `{selected_recon.observed_candidate_span:,}` B")
            st.markdown(f"**Structural Validity:** `{selected_recon.structural_validity * 100:.1f}%` ({selected_recon.parser_validation_status})")
            st.markdown(f"**Parser Diagnostic:** {selected_recon.parser_message or 'No parser message'}")

            st.markdown("##### Forensic Identity")
            st.text_input("Candidate SHA-256 Digest", value=selected_recon.output_sha256 or "N/A", disabled=True)
            st.markdown(f"**Artifact Path:** `{selected_recon.output_path or 'Not saved to disk'}`")

            # Download button if artifact exists
            if selected_recon.output_path and os.path.exists(selected_recon.output_path):
                try:
                    with open(selected_recon.output_path, "rb") as af:
                        file_bytes = af.read()
                    cand_name = Path(selected_recon.output_path).name
                    st.download_button(
                        label=f"⬇️ Download Artifact ({cand_name})",
                        data=file_bytes,
                        file_name=cand_name,
                        mime="application/octet-stream",
                        type="primary",
                        use_container_width=True,
                    )
                except Exception as dl_err:
                    st.error(f"Failed to prepare download: {dl_err}")
            else:
                st.warning("Artifact file not found on disk.")

        with col_right:
            render_file_preview(selected_recon.output_path, file_type=selected_recon.file_type)
