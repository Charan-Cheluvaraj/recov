import streamlit as st
from typing import Optional
from models.ranked_results import RankedResults

def render_overview(results: Optional[RankedResults] = None) -> None:
    """Render high-level executive summary metrics and dataset overview."""
    st.header("Executive Summary & Overview")
    if not results:
        st.info("No active pipeline results loaded. Upload an evidence image or load cached run.")
        st.metric(label="Total Fragments Carved", value=0)
        st.metric(label="Reconstructed Files", value=0)
        st.metric(label="Average Integrity Score", value="0.0%")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Evidence Hash", results.evidence_image_hash[:12] if results.evidence_image_hash else "N/A")
        col2.metric("Total Files", len(results.files))
        col3.metric("Clusters", len(results.clusters))
        col4.metric("Orphan Fragments", len(results.orphans))
