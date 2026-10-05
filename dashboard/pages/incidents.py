"""Incidents page — table with filters + severity/state charts."""
from __future__ import annotations

import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dashboard.data_bridge import get_incidents, get_incident_states, get_incident_categories
from dashboard.charts import severity_pie, state_bar


def render() -> None:
    st.header("🚨 Incidents")

    df = get_incidents()

    if df.empty or "_error" in df.columns:
        st.warning(
            "No incident data loaded. "
            "Download `incident_event_log.csv` from Kaggle and place it in "
            "`opsmind/data/datasets/incidents/`."
        )
        st.info("Showing demo charts with synthetic data.")
        _render_demo_charts()
        return

    # ── Filters ──────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        states = ["All"] + sorted(df["state"].dropna().unique().tolist()) if "state" in df.columns else ["All"]
        sel_state = st.selectbox("State", states)
    with col2:
        cats = ["All"] + sorted(df["category"].dropna().unique().tolist()) if "category" in df.columns else ["All"]
        sel_cat = st.selectbox("Category", cats)
    with col3:
        pris = ["All"] + sorted(df["priority"].dropna().unique().tolist()) if "priority" in df.columns else ["All"]
        sel_pri = st.selectbox("Priority", pris)

    filtered = df.copy()
    if sel_state != "All" and "state" in filtered.columns:
        filtered = filtered[filtered["state"] == sel_state]
    if sel_cat != "All" and "category" in filtered.columns:
        filtered = filtered[filtered["category"] == sel_cat]
    if sel_pri != "All" and "priority" in filtered.columns:
        filtered = filtered[filtered["priority"] == sel_pri]

    st.caption(f"Showing {len(filtered)} of {len(df)} incidents")

    # ── Charts ────────────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        cats_counts = get_incident_categories()
        if cats_counts:
            st.plotly_chart(severity_pie(cats_counts), use_container_width=True)
    with c2:
        state_counts = get_incident_states()
        if state_counts:
            st.plotly_chart(state_bar(state_counts), use_container_width=True)

    # ── Table ─────────────────────────────────────────────────────────────
    display_cols = [c for c in ["number", "state", "category", "priority",
                                "short_description", "opened_at", "resolved_at",
                                "severity_score"] if c in filtered.columns]
    st.dataframe(
        filtered[display_cols] if display_cols else filtered,
        use_container_width=True,
        height=400,
    )


def _render_demo_charts() -> None:
    from dashboard.charts import severity_pie, state_bar
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(severity_pie({"network": 23, "database": 15, "software": 41, "hardware": 8}), use_container_width=True)
    with c2:
        st.plotly_chart(state_bar({"New": 12, "In Progress": 8, "Resolved": 45, "Closed": 30}), use_container_width=True)
