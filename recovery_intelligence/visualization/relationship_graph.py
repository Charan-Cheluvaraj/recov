import streamlit as st
from typing import Dict, Any, Optional

def render_relationship_graph(graph_data: Optional[Dict[str, Any]] = None) -> None:
    """Render interactive fragment relationship graph using Graphviz or clean structured view."""
    st.header("Fragment Relationship Graph")
    if not graph_data or not graph_data.get("nodes"):
        st.info("No relationship graph data available. Run Stage 4 to construct fragment connections.")
        return

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    col1, col2 = st.columns(2)
    col1.metric("Graph Nodes", len(nodes))
    col2.metric("Relationship Edges", len(edges))

    st.caption(f"Visualizing correlation edges with weight >= threshold.")

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
            sim = edge.get("similarity", 0.0)
            edge_label = f"w:{w:.2f}\nsim:{sim:.2f}"
            dot.edge(src, tgt, label=edge_label, fontname="Helvetica", fontsize="9")

        st.graphviz_chart(dot, use_container_width=True)
    except Exception:
        # Fallback table visualization if graphviz executable is not installed
        st.subheader("Relationship Edges Table")
        st.dataframe(edges, use_container_width=True)