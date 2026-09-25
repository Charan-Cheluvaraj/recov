import streamlit as st
from typing import Optional
from models.reconstructed_file import ReconstructedFile


def render_integrity_signals(file: Optional[ReconstructedFile] = None) -> None:
    """
    Render four isolated integrity signals plus composite score with explicit explanatory labels.
    
    Signals remain independent engineering measurements; none are presented as certainty or probability.
    """
    st.subheader("Decomposed Integrity Signals")
    if not file:
        st.info("Select a candidate file to inspect its decomposed integrity signals.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### 1. Reconstruction Confidence")
        st.caption("Evidence supporting the fragment grouping/order.")
        conf_pct = file.reconstruction_confidence * 100
        st.progress(max(0.0, min(1.0, file.reconstruction_confidence)))
        st.markdown(f"**{conf_pct:.1f}%** (Score: `{file.reconstruction_confidence:.4f}`)")

        st.markdown("##### 2. Completeness")
        st.caption("Observed/estimated amount of recoverable structure present.")
        comp_pct = file.completeness * 100
        st.progress(max(0.0, min(1.0, file.completeness)))
        st.markdown(f"**{comp_pct:.1f}%** (Score: `{file.completeness:.4f}`)")

    with col2:
        st.markdown("##### 3. Structural Validity")
        st.caption("Result of the actual format parser check.")
        val_pct = file.structural_validity * 100
        st.progress(max(0.0, min(1.0, file.structural_validity)))
        st.markdown(f"**{val_pct:.1f}%** (Score: `{file.structural_validity:.4f}`)")

        st.markdown("##### 4. Corruption Estimate")
        st.caption("Observed evidence suggesting damaged/corrupted content (0% = clean, 100% = severe).")
        corr_pct = file.corruption_estimate * 100
        st.progress(max(0.0, min(1.0, file.corruption_estimate)))
        st.markdown(f"**{corr_pct:.1f}%** (Score: `{file.corruption_estimate:.4f}`)")

    st.markdown("---")
    st.markdown("##### Composite Integrity Score (Prioritization & Sorting)")
    st.caption("Weighted sorting score derived from the four signals. Used for sorting, not an absolute truth claim.")
    integ_pct = file.composite_integrity_score * 100
    st.progress(max(0.0, min(1.0, file.composite_integrity_score)))
    st.metric("Composite Integrity Score", f"{integ_pct:.1f}%", help="Derived from 4 independent signals")
