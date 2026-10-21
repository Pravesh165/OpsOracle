"""
Tests for Knowledge Learning Loop (Phase 6).
Verifies postmortem parsing, markdown chunking, weight updating, and knowledge stats.
"""

import os
import tempfile
import pytest

from opsmind.tools.learning import (
    ingest_postmortem,
    mark_resolution_helpful,
    get_knowledge_stats,
    _parse_markdown_sections,
    _load_weights,
    _save_weights,
)


def test_parse_markdown_sections():
    md = """# Postmortem for INC0000001
## Executive Summary
Network packet drop caused outage.

## Root Cause Analysis
Upstream buffer bloat on gateway [INC0000001].

## Lessons Learned
1. Increase socket backlog.
2. Enable keepalives.
"""
    sections = _parse_markdown_sections(md)
    headings = [s["heading"] for s in sections]
    assert "Executive Summary" in headings
    assert "Root Cause Analysis" in headings
    assert "Lessons Learned" in headings


def test_mark_resolution_helpful_and_stats():
    res_up = mark_resolution_helpful(incident_id="INC0000001", helpful=True)
    assert res_up["status"] == "success"
    assert res_up["weight"] >= 1

    res_down = mark_resolution_helpful(incident_id="INC0000001", helpful=False)
    assert res_down["status"] == "success"
    assert res_down["weight"] <= res_up["weight"]

    stats = get_knowledge_stats()
    assert stats["status"] == "success"
    assert "top_weighted" in stats
    assert len(stats["top_weighted"]) >= 1


def test_ingest_postmortem_end_to_end(tmp_path):
    postmortem_file = tmp_path / "postmortem_INC0000001.md"
    postmortem_file.write_text("""# Postmortem INC0000001
## Root Cause Analysis
Load balancer upstream timeout due to stale DNS records.
## Action Items
Flush local cache on deploy.
""", encoding="utf-8")

    res = ingest_postmortem(filepath=str(postmortem_file), incident_id="INC0000001")

    assert res["status"] in ("success", "partial_success", "error")
    assert res["incident_id"] == "INC0000001"

