import streamlit as st
from typing import Dict, Any, Optional

def render_relationship_graph(graph_data: Optional[Dict[str, Any]] = None) -> None:
    """Render interactive fragment relationship graph distinguishing structural vs heuristic edges."""
    st.header("Fragment Relationship Graph")
    if not graph_data or not graph_data.get("nodes"):
        st.info("No relationship graph data available. Run Stage 4 to construct fragment connections.")
        return

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    col1, col2, col3 = st.columns(3)
    struct_edges = sum(1 for e in edges if e.get("relationship_basis") in ("STRUCTURAL_SPATIAL", "FILESYSTEM_EXTENT"))
    heur_edges = sum(1 for e in edges if e.get("relationship_basis") == "HEURISTIC_SIMILARITY")

    col1.metric("Graph Nodes", len(nodes))
    col2.metric("Structural Edges", struct_edges)
    col3.metric("Heuristic Edges", heur_edges)

    st.caption("Visualizing fragment relationships: **Solid/Blue** = Structural/Spatial Proximity, **Dashed/Gray** = Heuristic Similarity.")

    if not edges:
        st.warning("No relationship edges above the minimum weight threshold were found.")
        return

    # Render graph using graphviz Digraph if possible
    try:
        import graphviz
        dot = graphviz.Graph(comment="Fragment Relationships", engine="dot")
        dot.attr(rankdir="LR", bgcolor="transparent")

        for node in nodes:
            nid = node["id"]
            ntype = node.get("type_hint", "unknown").upper()
            nchar = node.get("characterization", "binary")
            color = "#c8e6c9" if nchar == "text" else "#bbdefb"
            label = f"{nid}\n[{ntype}]"
            dot.node(nid, label=label, shape="box", style="rounded,filled", fillcolor=color, fontname="Helvetica")

        for edge in edges:
            src = edge["source"]
            tgt = edge["target"]
            w = edge.get("edge_weight", 0.0)
            basis = edge.get("relationship_basis", "HEURISTIC_SIMILARITY")
            style = "solid" if basis in ("STRUCTURAL_SPATIAL", "FILESYSTEM_EXTENT") else "dashed"
            color = "#1976d2" if basis in ("STRUCTURAL_SPATIAL", "FILESYSTEM_EXTENT") else "#9e9e9e"
            edge_label = f"w:{w:.2f}\n{basis[:4]}"
            dot.edge(src, tgt, label=edge_label, style=style, color=color, fontname="Helvetica", fontsize="8")

        st.graphviz_chart(dot, use_container_width=True)
    except Exception:
        pass

    st.subheader("Relationship Edges Table")
    st.dataframe(edges, use_container_width=True)