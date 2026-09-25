import streamlit as st
import sys
from pathlib import Path
from typing import Optional

# Add project root directory to python path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import settings
from models.evidence import Evidence
from models.fragment import Fragment
from visualization import (
    render_overview,
    render_ranked_results,
    render_file_detail,
    render_relationship_graph,
    render_integrity_signals,
    render_narrative,
)
from storage import load_cached_results
from pipeline import run_pipeline, run_stage_1, run_stage_2

st.set_page_config(
    page_title="AI-Assisted Intelligent Data Recovery",
    page_icon="🔍",
    layout="wide",
)

st.title("AI-Assisted Intelligent Data Recovery & Digital Evidence Reconstruction")
st.caption("CALMSTACKS 24H HACKATHON Project | Stage 1 + Stage 2: Evidence Ingestion, Magic-Byte Carving & Fragment Characterization")

# Ensure required directories exist
settings.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Session state initialization
if "evidence_record" not in st.session_state:
    st.session_state.evidence_record = None
if "carved_fragments" not in st.session_state:
    st.session_state.carved_fragments = []
if "characterized_fragments" not in st.session_state:
    st.session_state.characterized_fragments = []
if "current_results" not in st.session_state:
    st.session_state.current_results = None

# Sidebar Controls
st.sidebar.title("Forensic Controls")
st.sidebar.markdown("---")

view_mode = st.sidebar.radio(
    "Select Dashboard View",
    ["Stage 1: Carving", "Stage 2: Characterization", "Overview", "Ranked Results", "File Detail", "Relationship Graph", "Narrative Report"],
)

st.sidebar.markdown("---")
st.sidebar.subheader("Evidence Ingestion")

# File Selection / Upload
evidence_files = sorted(
    list(settings.EVIDENCE_DIR.glob("*.dd"))
    + list(settings.EVIDENCE_DIR.glob("*.img"))
    + list(settings.EVIDENCE_DIR.glob("*.raw"))
    + list(settings.EVIDENCE_DIR.glob("*.bin"))
)

selected_evidence = st.sidebar.selectbox(
    "Select Local Evidence Image",
    options=["None"] + [f.name for f in evidence_files],
)

uploaded_file = st.sidebar.file_uploader(
    "Or Upload Evidence Segment",
    type=["dd", "img", "raw", "bin"],
)

st.sidebar.markdown("---")
st.sidebar.subheader("Cached Runs")
cache_files = list(settings.CACHE_DIR.glob("run_*.json"))
selected_cache = st.sidebar.selectbox(
    "Load Cached Pipeline Run",
    options=["None"] + [f.stem.replace("run_", "") for f in cache_files],
)

if selected_cache != "None" and st.sidebar.button("Load Cached Run"):
    results = load_cached_results(selected_cache)
    if results:
        st.session_state.current_results = results
        st.sidebar.success(f"Loaded run '{selected_cache}' successfully!")
    else:
        st.sidebar.error("Failed to load cached run.")

st.sidebar.markdown("---")

# Execution Buttons
col_btn1, col_btn2 = st.sidebar.columns(2)
run_stage1_clicked = col_btn1.button("Run Stage 1 Carve", type="primary")
run_stage2_clicked = col_btn2.button("Run Stage 2 Characterize", type="secondary")
st.sidebar.markdown("")
run_full_clicked = st.sidebar.button("Run Full Pipeline (Deferred)")

# Target Path Resolution
target_path: Optional[str] = None
if selected_evidence != "None":
    target_path = str(settings.EVIDENCE_DIR / selected_evidence)
elif uploaded_file is not None:
    dest_path = settings.EVIDENCE_DIR / uploaded_file.name
    with open(dest_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    target_path = str(dest_path)

if run_stage1_clicked:
    if not target_path:
        st.sidebar.warning("Please select or upload an evidence image first.")
    else:
        try:
            with st.spinner("Calculating SHA-256 and carving candidate fragments..."):
                evidence, fragments = run_stage_1(target_path)
                st.session_state.evidence_record = evidence
                st.session_state.carved_fragments = fragments
                st.sidebar.success(f"Carved {len(fragments)} fragments!")
        except Exception as e:
            st.sidebar.error(f"Stage 1 Ingestion Error: {e}")

if run_stage2_clicked:
    if not target_path:
        st.sidebar.warning("Please select or upload an evidence image first.")
    else:
        try:
            with st.spinner("Running Stage 2: entropy + characterization..."):
                evidence, characterized = run_stage_2(target_path)
                st.session_state.evidence_record = evidence
                st.session_state.carved_fragments = characterized
                st.session_state.characterized_fragments = characterized
                st.sidebar.success(f"Characterized {len(characterized)} fragments!")
        except Exception as e:
            st.sidebar.error(f"Stage 2 Characterization Error: {e}")

if run_full_clicked:
    if not target_path:
        st.sidebar.warning("Please select or upload an evidence image first.")
    else:
        with st.spinner("Executing 14-stage recovery pipeline..."):
            try:
                results = run_pipeline(target_path)
                st.session_state.current_results = results
                st.success("Pipeline execution complete!")
            except NotImplementedError as e:
                st.info(f"Notice: {e}")
            except Exception as e:
                st.error(f"Pipeline Error: {e}")

# Main Content Render
if view_mode == "Stage 1: Carving":
    st.header("Stage 1: Evidence Ingestion & Magic-Byte Carving")
    
    evidence: Optional[Evidence] = st.session_state.evidence_record
    fragments: list[Fragment] = st.session_state.carved_fragments
    
    if not evidence:
        st.info("No evidence image analyzed yet. Select or upload an evidence file from the sidebar and click 'Run Stage 1 Carve'.")
    else:
        # Evidence Metadata Cards
        st.subheader("Evidence Integrity & Source")
        c1, c2, c3 = st.columns([1, 1, 2])
        c1.metric("Evidence ID", evidence.evidence_id)
        c2.metric("Size (Bytes)", f"{evidence.metadata.get('size_bytes', 0):,}")
        c3.text_input("SHA-256 Cryptographic Hash", value=evidence.sha256, disabled=True)
        st.caption(f"Source Path: `{evidence.source_path}` | Ingested At: `{evidence.created_at}`")
        
        st.markdown("---")
        st.subheader("Carving Statistics")
        
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        stat_col1.metric("Total Candidates", len(fragments))
        jpeg_count = sum(1 for f in fragments if f.type_hint == "jpeg")
        pdf_count = sum(1 for f in fragments if f.type_hint == "pdf")
        zip_count = sum(1 for f in fragments if f.type_hint == "zip")
        sqlite_count = sum(1 for f in fragments if f.type_hint == "sqlite")
        
        stat_col2.metric("JPEG Candidates", jpeg_count)
        stat_col3.metric("PDF Candidates", pdf_count)
        stat_col4.metric("ZIP / SQLite", f"{zip_count} ZIP / {sqlite_count} SQLite")
        
        st.markdown("---")
        st.subheader("Carved Fragments Table")
        
        if not fragments:
            st.warning("No candidate fragments matching supported signatures were found in this evidence file.")
        else:
            table_data = [
                {
                    "Fragment ID": f.id,
                    "Offset": f"{f.offset} (0x{f.offset:08X})",
                    "Length": f"{f.length} B",
                    "Type Hint": f.type_hint.upper(),
                    "Header": "✓ Found" if f.header_flag else "✗ Missing",
                    "Footer": "✓ Found" if f.footer_flag else "—",
                    "Source": Path(f.source).name,
                }
                for f in fragments
            ]
            st.dataframe(table_data, use_container_width=True)
            
            with st.expander("Inspect Raw Fragment Metadata (JSON)"):
                st.json([f.model_dump() for f in fragments])

elif view_mode == "Stage 2: Characterization":
    st.header("Stage 2: Fragment Characterization (Entropy Analysis)")
    fragments = st.session_state.characterized_fragments

    if not fragments:
        st.info(
            "No characterized fragments yet. Select an evidence file and click "
            "**Run Stage 2 Characterize** in the sidebar."
        )
    else:
        evidence = st.session_state.evidence_record
        if evidence:
            st.caption(
                f"Evidence: `{evidence.source_path}` | SHA-256: `{evidence.sha256[:16]}…` | "
                f"{len(fragments)} fragments characterized"
            )

        # Summary metrics
        text_c = sum(1 for f in fragments if f.metadata.get("characterization") == "text")
        binary_c = sum(1 for f in fragments if f.metadata.get("characterization") == "binary")
        mixed_c = sum(1 for f in fragments if f.metadata.get("characterization") == "mixed")
        avg_entropy = sum(f.entropy for f in fragments) / len(fragments) if fragments else 0.0

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Fragments", len(fragments))
        m2.metric("Text", text_c)
        m3.metric("Binary", binary_c)
        m4.metric("Mixed", mixed_c)
        m5.metric("Avg Entropy", f"{avg_entropy:.3f}")

        st.markdown("---")
        st.subheader("Characterized Fragments Table")

        table_data = [
            {
                "Fragment ID": f.id,
                "Offset": f"{f.offset} (0x{f.offset:08X})",
                "Length": f"{f.length} B",
                "Type Hint": f.type_hint.upper(),
                "Entropy": f"{f.entropy:.4f}",
                "Characterization": f.metadata.get("characterization", "-").upper(),
                "Printable Ratio": f"{f.metadata.get('printable_ratio', 0.0):.3f}",
                "Header": "✓" if f.header_flag else "✗",
                "Footer": "✓" if f.footer_flag else "—",
            }
            for f in fragments
        ]
        st.dataframe(table_data, use_container_width=True)

        st.markdown("---")
        st.subheader("Entropy Window Chart (Select Fragment)")

        frag_ids = [f.id for f in fragments]
        selected_id = st.selectbox("Select fragment to inspect:", frag_ids)
        selected_frag = next((f for f in fragments if f.id == selected_id), None)

        if selected_frag:
            windows = selected_frag.metadata.get("entropy_windows", [])
            if windows:
                chart_data = {
                    "Byte Offset": [w["start"] for w in windows],
                    "Window Entropy": [w["entropy"] for w in windows],
                }
                import pandas as pd
                df = pd.DataFrame(chart_data).set_index("Byte Offset")
                st.line_chart(df, height=250)
                st.caption(
                    f"Whole-fragment entropy: **{selected_frag.entropy:.4f}** | "
                    f"Characterization: **{selected_frag.metadata.get('characterization', '-').upper()}** | "
                    f"Printable ratio: **{selected_frag.metadata.get('printable_ratio', 0.0):.3f}**"
                )
            else:
                st.info("No sliding-window data available for this fragment.")

elif view_mode == "Overview":
    render_overview(st.session_state.current_results)
elif view_mode == "Ranked Results":
    render_ranked_results(st.session_state.current_results)
elif view_mode == "File Detail":
    selected_file = st.session_state.current_results.files[0] if (st.session_state.current_results and st.session_state.current_results.files) else None
    render_file_detail(selected_file)
    if selected_file:
        render_integrity_signals(selected_file)
elif view_mode == "Relationship Graph":
    graph_data = st.session_state.current_results.relationship_graph if hasattr(st.session_state.current_results, "relationship_graph") else None
    render_relationship_graph(graph_data)
elif view_mode == "Narrative Report":
    narrative_data = getattr(st.session_state.current_results, "narrative", None)
    render_narrative(narrative_data)
