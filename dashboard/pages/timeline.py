"""Timeline page — incident event timeline with Mermaid sequence diagram."""
from __future__ import annotations

import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dashboard.data_bridge import get_incidents, get_incident_timeline


def _mermaid_sequence(events: list) -> str:
    """Build a Mermaid sequence diagram string from timeline events."""
    lines = ["sequenceDiagram", "    participant System", "    participant Team"]
    for ev in events:
        ts = ev["timestamp"][:16] if len(ev["timestamp"]) >= 16 else ev["timestamp"]
        label = ev["event"].replace('"', "'")
        detail = ev["detail"][:60].replace('"', "'") if ev["detail"] else ""
        note = f" ({detail})" if detail else ""
        lines.append(f'    System->>Team: [{ts}] {label}{note}')
    return "\n".join(lines)


def render() -> None:
    st.header("🕐 Incident Timeline")

    # ── Incident selector ─────────────────────────────────────────────────
    df = get_incidents()
    incident_ids: list = []
    if not df.empty and "number" in df.columns:
        incident_ids = df["number"].dropna().unique().tolist()[:50]

    if incident_ids:
        selected = st.selectbox("Select Incident", incident_ids)
    else:
        selected = st.text_input("Incident ID", value="INC0000001")

    if not selected:
        st.info("Enter or select an incident ID to view its timeline.")
        return

    events = get_incident_timeline(str(selected))

    # ── Vertical step timeline ────────────────────────────────────────────
    st.subheader(f"Timeline: {selected}")
    st.caption(f"{len(events)} events")

    for i, ev in enumerate(events):
        col_icon, col_body = st.columns([1, 11])
        with col_icon:
            icon = "🔴" if i == 0 else ("🟢" if i == len(events) - 1 else "🔵")
            st.markdown(f"### {icon}")
        with col_body:
            st.markdown(f"**{ev['event']}**  \n`{ev['timestamp']}`")
            if ev.get("detail"):
                st.caption(ev["detail"])
        if i < len(events) - 1:
            st.markdown("<div style='margin-left:28px;border-left:2px solid #e2e8f0;height:16px'></div>",
                        unsafe_allow_html=True)

    st.divider()

    # ── Mermaid diagram (rendered as code block — Streamlit doesn't natively render Mermaid) ──
    with st.expander("📐 Mermaid Sequence Diagram (copy to mermaid.live)"):
        mermaid_src = _mermaid_sequence(events)
        st.code(mermaid_src, language="text")
        st.caption("Paste the above into https://mermaid.live to render interactively.")
