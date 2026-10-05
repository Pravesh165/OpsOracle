"""Analytics page — MTTR trend, category distribution, recurring patterns."""
from __future__ import annotations

import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dashboard.data_bridge import get_mttr_data, get_recurring_patterns, get_incident_categories
from dashboard.charts import mttr_trend, category_bar, recurring_patterns_bar


def render() -> None:
    st.header("📊 Analytics")

    # ── MTTR ──────────────────────────────────────────────────────────────
    st.subheader("Mean Time to Resolve (MTTR)")
    mttr_df = get_mttr_data()
    st.plotly_chart(mttr_trend(mttr_df), use_container_width=True)

    # ── KPI row ───────────────────────────────────────────────────────────
    if not mttr_df.empty:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Avg MTTR", f"{mttr_df['mttr_hours'].mean():.1f} h")
        with c2:
            st.metric("Best Category", mttr_df.loc[mttr_df['mttr_hours'].idxmin(), 'category'])
        with c3:
            st.metric("Total Incidents", int(mttr_df['incident_count'].sum()))

    st.divider()

    # ── Category distribution ─────────────────────────────────────────────
    st.subheader("Incident Distribution by Category")
    cats = get_incident_categories()
    if cats:
        st.plotly_chart(category_bar(cats), use_container_width=True)
    else:
        st.info("No category data available.")

    st.divider()

    # ── Recurring patterns ────────────────────────────────────────────────
    st.subheader("Top Recurring Patterns")
    patterns_df = get_recurring_patterns()
    st.plotly_chart(recurring_patterns_bar(patterns_df), use_container_width=True)
    st.dataframe(patterns_df, use_container_width=True, hide_index=True)
