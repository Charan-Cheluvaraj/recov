import streamlit as st
from typing import Optional
from models.reconstructed_file import ReconstructedFile

def render_file_detail(file: Optional[ReconstructedFile] = None) -> None:
    """Render deep-dive view for a single candidate file including fragments, gaps, and hex view."""
    st.header("Candidate File Detailed View")
    if not file:
        st.info("Select a candidate file from Ranked Results to view deep-dive analysis.")
    else:
        st.subheader(f"Candidate ID: {file.id} ({file.file_type})")
        st.json(file.model_dump())
