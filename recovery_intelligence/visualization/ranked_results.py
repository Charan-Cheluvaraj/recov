import streamlit as st
from typing import Optional
from models.ranked_results import RankedResults

def render_ranked_results(results: Optional[RankedResults] = None) -> None:
    """Render prioritized candidate file recovery table with signal scores."""
    st.header("Ranked Candidate Results")
    if not results or not results.files:
        st.info("No reconstructed candidate files available to display.")
    else:
        st.write(f"Displaying {len(results.files)} candidate reconstructed files:")
        for idx, file in enumerate(results.files):
            with st.expander(f"File #{idx+1} [{file.file_type}] - Composite Score: {file.composite_integrity_score:.2f}"):
                st.json(file.model_dump())
