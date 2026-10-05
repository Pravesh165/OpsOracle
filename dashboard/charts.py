"""
Plotly chart helpers for the OpsMind dashboard.

No Streamlit imports here — all functions return go.Figure objects.
Pages call st.plotly_chart(fig) themselves.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

try:
    import plotly.express as px
    import plotly.graph_objects as go
    _PLOTLY = True
except ImportError:
    _PLOTLY = False


def _no_plotly() -> None:
    raise ImportError("plotly is required. Run: pip install plotly>=5.20.0")


# ---------------------------------------------------------------------------
# Severity / state charts
# ---------------------------------------------------------------------------

def severity_pie(category_counts: Dict[str, int]):
    """Pie chart of incident counts by category."""
    if not _PLOTLY:
        _no_plotly()
    labels = list(category_counts.keys())
    values = list(category_counts.values())
    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.35,
        marker_colors=px.colors.qualitative.Set2,
    ))
    fig.update_layout(
        title="Incidents by Category",
        margin=dict(t=40, b=10, l=10, r=10),
        height=320,
    )
    return fig


def state_bar(state_counts: Dict[str, int]):
    """Horizontal bar chart of incident counts by state."""
    if not _PLOTLY:
        _no_plotly()
    states = list(state_counts.keys())
    counts = list(state_counts.values())
    _color_map = {
        "New": "#ef4444", "In Progress": "#f59e0b", "Resolved": "#22c55e",
        "Closed": "#6b7280", "On Hold": "#8b5cf6",
    }
    colors = [_color_map.get(s, "#60a5fa") for s in states]
    fig = go.Figure(go.Bar(
        x=counts, y=states, orientation="h",
        marker_color=colors,
        text=counts, textposition="outside",
    ))
    fig.update_layout(
        title="Incidents by State",
        xaxis_title="Count",
        margin=dict(t=40, b=10, l=10, r=10),
        height=max(200, len(states) * 40 + 60),
    )
    return fig


# ---------------------------------------------------------------------------
# Analytics charts
# ---------------------------------------------------------------------------

def mttr_trend(mttr_df: pd.DataFrame):
    """
    Horizontal bar chart of mean-time-to-resolve per category.

    Expects columns: category, mttr_hours, incident_count.
    """
    if not _PLOTLY:
        _no_plotly()
    if mttr_df.empty:
        fig = go.Figure()
        fig.update_layout(title="MTTR by Category (no data)")
        return fig

    fig = px.bar(
        mttr_df,
        x="mttr_hours",
        y="category",
        orientation="h",
        color="mttr_hours",
        color_continuous_scale="RdYlGn_r",
        text="mttr_hours",
        hover_data=["incident_count"],
        labels={"mttr_hours": "MTTR (hours)", "category": "Category"},
        title="Mean Time to Resolve by Category",
    )
    fig.update_traces(texttemplate="%{text:.1f}h", textposition="outside")
    fig.update_layout(
        coloraxis_showscale=False,
        margin=dict(t=50, b=10, l=10, r=10),
        height=max(250, len(mttr_df) * 45 + 80),
    )
    return fig


def category_bar(category_counts: Dict[str, int]):
    """Vertical bar chart of incident counts by category."""
    if not _PLOTLY:
        _no_plotly()
    cats = list(category_counts.keys())
    counts = list(category_counts.values())
    fig = px.bar(
        x=cats, y=counts,
        labels={"x": "Category", "y": "Count"},
        title="Incident Count by Category",
        color=counts,
        color_continuous_scale="Blues",
    )
    fig.update_layout(
        coloraxis_showscale=False,
        margin=dict(t=50, b=10, l=10, r=10),
        height=320,
    )
    return fig


def recurring_patterns_bar(patterns_df: pd.DataFrame):
    """Bar chart of top recurring incident patterns."""
    if not _PLOTLY:
        _no_plotly()
    if patterns_df.empty:
        fig = go.Figure()
        fig.update_layout(title="Recurring Patterns (no data)")
        return fig
    fig = px.bar(
        patterns_df,
        x="count",
        y="pattern",
        orientation="h",
        color="avg_severity",
        color_continuous_scale="RdYlGn_r",
        labels={"count": "Occurrences", "pattern": "Pattern", "avg_severity": "Avg Severity"},
        title="Top Recurring Incident Patterns",
    )
    fig.update_layout(
        margin=dict(t=50, b=10, l=10, r=10),
        height=max(250, len(patterns_df) * 40 + 80),
    )
    return fig


# ---------------------------------------------------------------------------
# Knowledge stats chart
# ---------------------------------------------------------------------------

def knowledge_sources_pie(sources: Dict[str, int]):
    """Pie chart of knowledge base document sources."""
    if not _PLOTLY:
        _no_plotly()
    if not sources:
        fig = go.Figure()
        fig.update_layout(title="Knowledge Sources (index empty)")
        return fig
    labels = list(sources.keys())
    values = list(sources.values())
    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.4,
        marker_colors=px.colors.qualitative.Pastel,
    ))
    fig.update_layout(
        title="Knowledge Base Sources",
        margin=dict(t=40, b=10, l=10, r=10),
        height=300,
    )
    return fig
