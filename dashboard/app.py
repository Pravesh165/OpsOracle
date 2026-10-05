"""
OpsMind Dashboard — Phase 7
Run with: streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
import os

# Ensure project root is on path so opsmind.* imports work
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

# Page config must be the first Streamlit call
st.set_page_config(
    page_title="OpsMind Dashboard",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Overview page (defined before routing so it can be called below)
# ---------------------------------------------------------------------------

def _render_overview() -> None:
    st.header("🏠 Overview")
    st.caption("OpsMind — *From Incident to Insight, Autonomously* ⚡")

    from dashboard.data_bridge import (
        get_incidents,
        get_postmortems,
        get_knowledge_stats,
        get_mttr_data,
        get_incident_categories,
        get_incident_states,
    )
    from dashboard.charts import severity_pie, state_bar

    inc_df  = get_incidents()
    pms     = get_postmortems()
    kstats  = get_knowledge_stats()
    mttr_df = get_mttr_data()

    # KPI row
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Total Incidents", len(inc_df) if not inc_df.empty else 0)
    with c2:
        active = 0
        if not inc_df.empty and "state" in inc_df.columns:
            active = int(
                (~inc_df["state"].str.lower().isin(["resolved", "closed"])).sum()
            )
        st.metric("Active Incidents", active)
    with c3:
        st.metric("Postmortems", len(pms))
    with c4:
        avg_mttr = (
            f"{mttr_df['mttr_hours'].mean():.1f} h" if not mttr_df.empty else "N/A"
        )
        st.metric("Avg MTTR", avg_mttr)
    with c5:
        st.metric("KB Documents", kstats.get("total_documents", 0))

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        cats = get_incident_categories()
        if cats:
            st.plotly_chart(severity_pie(cats), use_container_width=True)
        else:
            st.info("No incident category data.")
    with col2:
        states = get_incident_states()
        if states:
            st.plotly_chart(state_bar(states), use_container_width=True)
        else:
            st.info("No incident state data.")

    st.divider()

    if pms:
        st.subheader("Recent Postmortems")
        for pm in pms[:3]:
            st.markdown(
                f"📄 **{pm['filename']}** — {pm['modified']} — "
                f"Incident: `{pm['incident_id']}`"
            )
    else:
        st.info("No postmortems generated yet.")


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

PAGES = {
    "🏠 Overview":        "overview",
    "🚨 Incidents":       "incidents",
    "📋 Postmortems":     "postmortems",
    "📊 Analytics":       "analytics",
    "🕐 Timeline":        "timeline",
    "🧠 Knowledge Stats": "knowledge",
}

with st.sidebar:
    st.title("🧠 OpsMind")
    st.caption("SRE/DevOps Incident Copilot")
    st.divider()
    selection = st.radio(
        "Navigate", list(PAGES.keys()), label_visibility="collapsed"
    )
    st.divider()
    st.caption("💡 Run `adk web` to open the AI chat interface.")

page_key = PAGES[selection]

# ---------------------------------------------------------------------------
# Page routing
# ---------------------------------------------------------------------------

if page_key == "overview":
    _render_overview()
elif page_key == "incidents":
    from dashboard.pages.incidents import render
    render()
elif page_key == "postmortems":
    from dashboard.pages.postmortems import render
    render()
elif page_key == "analytics":
    from dashboard.pages.analytics import render
    render()
elif page_key == "timeline":
    from dashboard.pages.timeline import render
    render()
elif page_key == "knowledge":
    from dashboard.pages.knowledge import render
    render()
