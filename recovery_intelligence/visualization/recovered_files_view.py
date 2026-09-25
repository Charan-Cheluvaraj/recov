import os
from pathlib import Path
from typing import List, Optional
import streamlit as st

from models.reconstructed_file import ReconstructedFile
from .file_preview import render_file_preview


def render_recovered_files_view(reconstructed_list: Optional[List[ReconstructedFile]] = None) -> None:
    """Render dedicated Recovered Files view with interactive table, inspection, and multi-format preview."""
    st.header("Recovered Files & Artifact Inspection")
    st.caption("Inspect and download reconstructed digital evidence artifacts with forensic integrity and recoverability metrics.")

    if not reconstructed_list:
        st.info("No recovered file artifacts available. Select an evidence image and click 'RUN FULL RECOVERY ANALYSIS'.")
        return

    # 1. High-Level Summary Metrics
    c1, c2, c3, c4 = st.columns(4)
    total_candidates = len(reconstructed_list)
    artifacts_on_disk = sum(1 for r in reconstructed_list if r.output_path and os.path.exists(r.output_path))
    avg_ratio = (
        sum(r.observed_recovery_ratio for r in reconstructed_list) / max(1, total_candidates)
    )
    total_rec_bytes = sum(r.recovered_bytes for r in reconstructed_list)

    c1.metric("Total Candidates", total_candidates)
    c2.metric("Artifacts on Disk", artifacts_on_disk)
    c3.metric("Avg Observed Recovery Ratio", f"{avg_ratio * 100:.1f}%")
    c4.metric("Total Recovered Bytes", f"{total_rec_bytes:,} B")

    st.markdown("---")

    # 2. Recovered Files Table
    st.subheader("All Recovered File Candidates")

    table_rows = [
        {
            "Rank": idx + 1,
            "Candidate ID": r.candidate_id or r.id,
            "File Type": r.file_type.upper(),
            "Recovery Status": r.recovery_status or r.status,
            "Recovered Bytes": f"{r.recovered_bytes:,} B",
            "Missing/Unknown": f"{r.missing_or_unknown_bytes:,} B",
            "Observed Recovery Ratio": f"{r.observed_recovery_ratio * 100:.1f}%",
            "Integrity": f"{r.composite_integrity_score * 100:.1f}%",
            "Sensitivity": r.sensitivity_level or "NONE",
            "Priority": f"{r.priority_score:.4f}" if r.priority_score is not None else "0.0000",
            "Output SHA-256": r.output_sha256[:16] + "..." if r.output_sha256 else "—",
        }
        for idx, r in enumerate(reconstructed_list)
    ]
    st.dataframe(table_rows, use_container_width=True)

    st.markdown("---")

    # 3. Candidate Inspector, Preview, and Download
    st.subheader("Candidate Artifact Inspector")
    cand_options = [r.candidate_id or r.id for r in reconstructed_list]
    selected_id = st.selectbox("Select Candidate to Preview & Download", options=cand_options)
    selected_recon = next((r for r in reconstructed_list if (r.candidate_id or r.id) == selected_id), None)

    if selected_recon:
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown("##### Candidate Metadata")
            st.markdown(f"**Candidate ID:** `{selected_recon.candidate_id or selected_recon.id}`")
            st.markdown(f"**Associated Cluster:** `{selected_recon.cluster_id}`")
            st.markdown(f"**File Format:** `{selected_recon.file_type.upper()}`")
            st.markdown(f"**Recovery Status:** `{selected_recon.recovery_status}`")
            st.markdown(f"**Observed Recovery Ratio:** `{selected_recon.observed_recovery_ratio * 100:.2f}%` ({selected_recon.observed_recovery_ratio:.4f})")
            st.markdown(f"**Recovered Bytes:** `{selected_recon.recovered_bytes:,}` B")
            st.markdown(f"**Missing/Unknown Bytes:** `{selected_recon.missing_or_unknown_bytes:,}` B")
            st.markdown(f"**Observed Candidate Span:** `{selected_recon.observed_candidate_span:,}` B")
            st.markdown(f"**Structural Validity:** `{selected_recon.structural_validity * 100:.1f}%`")
            st.markdown(f"**Parser Diagnostic:** {selected_recon.parser_message or 'Valid format syntax'}")

            st.markdown("##### Forensic Identity")
            st.text_input("Candidate SHA-256 Digest", value=selected_recon.output_sha256 or "N/A", disabled=True)
            st.markdown(f"**Artifact File Path:** `{selected_recon.output_path or 'Not saved to disk'}`")

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
