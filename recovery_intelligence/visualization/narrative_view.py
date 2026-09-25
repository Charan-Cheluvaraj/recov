import streamlit as st
from typing import Optional
from models.narrative import Narrative

def render_narrative(narrative: Optional[Narrative] = None) -> None:
    """Render analyst-friendly investigative report with explicit Observed/Inferred/Unknown separation."""
    st.header("AI Investigative Narrative Report")
    if not narrative:
        st.info("No narrative report generated yet. Run pipeline analysis to generate narrative.")
    else:
        st.subheader("1. Observed Facts")
        st.write(narrative.observed)
        
        st.subheader("2. AI Inferences")
        st.write(narrative.inferred)
        
        st.subheader("3. Unknown / Ambiguous Gaps")
        st.write(narrative.unknown)
        
        st.subheader("4. Citations")
        st.write(narrative.citations)
