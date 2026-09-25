import streamlit as st
from typing import Optional, Any
from models.narrative import Narrative
from models.pipeline_result import PipelineResult


def render_narrative(narrative: Optional[Any] = None, pipeline_result: Optional[PipelineResult] = None) -> None:
    """Render analyst-friendly investigative report with strict forensic terminology and Observed/Inferred/Unknown separation."""
    st.header("AI Investigative Narrative Report")
    st.caption("Factual digital evidence reconstruction and triage report generated from forensic pipeline telemetry.")

    result = pipeline_result
    if result is None and isinstance(narrative, PipelineResult):
        result = narrative
        narrative = getattr(result, "narrative", None)

    if not narrative and not result:
        st.info("No narrative report generated yet. Run pipeline analysis to generate narrative.")
        return

    if narrative and isinstance(narrative, Narrative):
        st.subheader("1. Observed Facts")
        if isinstance(narrative.observed, list):
            for item in narrative.observed:
                st.markdown(f"- {item}")
        else:
            st.write(narrative.observed)

        st.subheader("2. Forensic Inferences")
        if isinstance(narrative.inferred, list):
            for item in narrative.inferred:
                st.markdown(f"- {item}")
        else:
            st.write(narrative.inferred)

        st.subheader("3. Unknown / Ambiguous Gaps")
        if isinstance(narrative.unknown, list):
            for item in narrative.unknown:
                st.markdown(f"- {item}")
        else:
            st.write(narrative.unknown)

        if getattr(narrative, "citations", None):
            st.subheader("4. Evidence Citations")
            st.write(narrative.citations)
        return

    # Auto-synthesize factual narrative if pipeline_result is available
    if result:
        total_frags = len(result.fragments)
        total_cands = len(result.reconstructed_files)
        val_cands = [r for r in result.reconstructed_files if r.is_successfully_recovered or r.recovery_state in ("FULL_RECOVERY", "VALIDATED_RECOVERY")]
        part_cands = [r for r in result.reconstructed_files if r.recovery_state == "PARTIAL_RECONSTRUCTION"]
        raw_cands = [r for r in result.reconstructed_files if r.recovery_state == "RAW_BINARY_RECOVERY"]
        inv_cands = [r for r in result.reconstructed_files if r.recovery_state in ("INVALID_RECONSTRUCTION", "UNRECOVERABLE")]

        st.subheader("1. Observed Forensic Facts")
        st.markdown(f"- Evidence image `{result.evidence_path}` (SHA-256: `{result.evidence_sha256}`) was ingested in read-only mode.")
        st.markdown(f"- **{total_frags}** fragments were carved from evidence using format-aware boundary detection.")
        st.markdown(f"- **{total_cands}** reconstruction candidates were generated across **{len(result.clusters)}** conservative clusters.")
        st.markdown(f"- **{len(val_cands)}** candidate(s) passed strict format parser validation and were classified as **VALIDATED RECOVERY**.")
        st.markdown(f"- **{len(part_cands)}** candidate(s) were classified as **PARTIAL RECONSTRUCTION** due to observed missing internal byte gaps.")
        st.markdown(f"- **{len(raw_cands)}** candidate(s) were classified as **RAW BINARY SALVAGE** (unvalidated raw stream).")
        st.markdown(f"- **{len(inv_cands)}** candidate(s) failed structural parser decoding and were classified as **INVALID RECONSTRUCTION**.")

        st.subheader("2. Forensic Inferences & Reconstruction Diagnostics")
        for r in result.reconstructed_files:
            cand_id = r.candidate_id or r.id
            st.markdown(f"- **Candidate `{cand_id}` ({r.file_type.upper()}):** {r.recovery_reason or r.parser_message}")

        st.subheader("3. Technical Limitations & Gaps")
        st.markdown("- **Non-Assertion Notice:** Candidates failing format-specific structural validation are preserved for forensic salvage but are not certified as recovered files.")
        st.markdown("- **Observed vs Logical Recovery:** Observed recovery ratio measures the fraction of recovered fragment bytes within the observed candidate span; logical recovery percentage requires filesystem metadata.")

