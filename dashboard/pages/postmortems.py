"""Postmortems page — list, inline viewer, download."""
from __future__ import annotations

import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dashboard.data_bridge import get_postmortems


def render() -> None:
    st.header("📋 Postmortems")

    postmortems = get_postmortems()

    if not postmortems:
        st.info(
            "No postmortem files found in `output/`. "
            "Generate one via the ADK chat: "
            "*\"Generate postmortem for incident INC0000045\"*"
        )
        return

    st.caption(f"{len(postmortems)} postmortem(s) found")

    # ── List ──────────────────────────────────────────────────────────────
    for pm in postmortems:
        with st.expander(
            f"📄 {pm['filename']}  —  {pm['modified']}  ({pm['size_kb']} KB)",
            expanded=False,
        ):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.caption(f"Incident: **{pm['incident_id']}**")
                st.caption(f"Preview: {pm['preview']}…")
            with col2:
                st.download_button(
                    label="⬇ Download",
                    data=pm["content"],
                    file_name=pm["filename"],
                    mime="text/markdown",
                    key=f"dl_{pm['filename']}",
                )

            st.markdown("---")
            st.markdown(pm["content"], unsafe_allow_html=False)
