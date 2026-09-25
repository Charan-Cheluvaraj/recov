from pathlib import Path
from typing import Optional, Union
import streamlit as st

from models.ranked_results import RankedResults
from models.pipeline_result import PipelineResult
from .signal_charts import render_integrity_signals


def render_ranked_results(results: Optional[Union[RankedResults, PipelineResult]] = None) -> None:
    """Render prioritized candidate file recovery table with priority scores, reason, and signal scores."""
    st.header("Investigative Priority Ranked Candidates")
    st.caption("Deterministic candidate ranking combining composite integrity, observed recoverability, format validity, and sensitivity classification.")

    files = []
    if isinstance(results, PipelineResult):
        files = results.reconstructed_files
    elif isinstance(results, RankedResults):
        files = results.files

    if not files:
        st.info("No reconstructed candidate files available to display. Run 'RUN FULL RECOVERY ANALYSIS' first.")
        return

    st.markdown(f"**Total Ranked Candidates:** `{len(files)}`")

    # Table displaying requested columns
    ranked_table = [
        {
            "Rank": idx + 1,
            "Candidate": r.candidate_id or r.id,
            "File Type": r.file_type.upper(),
            "Recovery Status": r.recovery_status or r.status,
            "Observed Recovery Ratio": f"{r.observed_recovery_ratio * 100:.1f}%",
            "Integrity": f"{r.composite_integrity_score * 100:.1f}%",
            "Sensitivity": r.sensitivity_level or "NONE",
            "Priority": f"{r.priority_score:.4f}" if r.priority_score is not None else "0.0000",
            "Reason": r.priority_reason or "—",
            "Output": Path(r.output_path).name if r.output_path else "—",
        }
        for idx, r in enumerate(files)
    ]
    st.dataframe(ranked_table, use_container_width=True)

    st.markdown("---")
    st.subheader("Candidate Inspection")

    cand_options = [r.candidate_id or r.id for r in files]
    chosen_id = st.selectbox("Select Candidate to Inspect Signals", options=cand_options)
    selected_file = next((r for r in files if (r.candidate_id or r.id) == chosen_id), None)

    if selected_file:
        col_l, col_r = st.columns([1, 1])
        with col_l:
            st.markdown("##### Priority Decision Rationale")
            st.info(selected_file.priority_reason or "No priority explanation available.")
            st.markdown(f"**Priority Score:** `{selected_file.priority_score:.4f}`")
            st.markdown(f"**Sensitivity Classification:** `{selected_file.sensitivity_level or 'NONE'}`")
            st.markdown(f"**Observed Recovery Ratio:** `{selected_file.observed_recovery_ratio * 100:.2f}%`")
            st.markdown(f"**Recovered Bytes:** `{selected_file.recovered_bytes:,} B`")
            st.markdown(f"**Missing/Unknown Bytes:** `{selected_file.missing_or_unknown_bytes:,} B`")
        with col_r:
            render_integrity_signals(selected_file)
