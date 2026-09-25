import streamlit as st
from typing import Optional
from models.reconstructed_file import ReconstructedFile

def render_integrity_signals(file: Optional[ReconstructedFile] = None) -> None:
    """Render four isolated integrity signals chart (Confidence, Completeness, Validity, Corruption)."""
    st.header("Four-Signal Integrity Analysis")
    if not file:
        st.info("Select a file to inspect four-signal breakdown.")
    else:
        st.metric("Relationship Confidence", f"{file.reconstruction_confidence * 100:.1f}%")
        st.metric("Completeness", f"{file.completeness * 100:.1f}%")
        st.metric("Structural Validity", f"{file.structural_validity * 100:.1f}%")
        st.metric("Corruption Estimate", f"{file.corruption_estimate * 100:.1f}%")
