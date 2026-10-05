"""Knowledge Stats page — retrieval index stats, source breakdown, top-weighted incidents."""
from __future__ import annotations

import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dashboard.data_bridge import get_knowledge_stats, get_recent_searches
from dashboard.charts import knowledge_sources_pie


def render() -> None:
    st.header("🧠 Knowledge Stats")

    stats = get_knowledge_stats()

    # ── Status banner ─────────────────────────────────────────────────────
    if stats.get("status") == "unavailable":
        st.warning(stats.get("message", "Knowledge index unavailable."))
    else:
        st.success("Knowledge index loaded ✅")

    # ── KPI row ───────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Documents", stats.get("total_documents", 0))
    with c2:
        st.metric("Postmortems Ingested", stats.get("postmortem_count", 0))
    with c3:
        st.metric("Index Loaded", "Yes" if stats.get("index_loaded") else "No")
    with c4:
        sources = stats.get("sources", {})
        st.metric("Source Types", len(sources))

    st.divider()

    # ── Source breakdown ──────────────────────────────────────────────────
    if sources:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("Source Breakdown")
            st.plotly_chart(knowledge_sources_pie(sources), use_container_width=True)
        with col2:
            st.subheader("Document Counts")
            import pandas as pd
            src_df = pd.DataFrame(
                [{"Source": k, "Documents": v} for k, v in sources.items()]
            ).sort_values("Documents", ascending=False)
            st.dataframe(src_df, use_container_width=True, hide_index=True)
    else:
        st.info(
            "No documents in index yet. "
            "Run `python scripts/build_index.py` to build the index from CSVs, "
            "or generate a postmortem to trigger auto-ingestion."
        )

    st.divider()

    # ── Top-weighted incidents ─────────────────────────────────────────────
    top = stats.get("top_weighted", [])
    if top:
        st.subheader("Top-Weighted Resolutions")
        st.caption("Incidents marked helpful by users (higher = more useful)")
        import pandas as pd
        tw_df = pd.DataFrame(top)
        st.dataframe(tw_df, use_container_width=True, hide_index=True)
    else:
        st.info(
            "No resolution weights recorded yet. "
            "Use `mark_resolution_helpful(incident_id, True)` after resolving incidents."
        )

    # ── Recent searches ───────────────────────────────────────────────────
    recent = get_recent_searches()
    if recent:
        st.divider()
        st.subheader("Recent Searches")
        for q in recent[:10]:
            st.markdown(f"- `{q}`")
