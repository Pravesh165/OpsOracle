"""
Regression and functional tests for Phase 0 bug fixes in data loader and context retrieval.
"""

import asyncio
import os
import sys
import pandas as pd
import pytest

_ROOT = os.path.dirname(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import opsmind.utils
from opsmind.data.loader import search_jira_issues
from opsmind.context.retrieval import get_incident_context


class FakeToolContext:
    def __init__(self):
        self.state = {}


def test_search_jira_issues_uses_summary_column(monkeypatch):
    """B5 regression test: search_jira_issues matches on summary or description."""
    mock_df = pd.DataFrame([
        {"id": "101", "key": "OPS-101", "summary": "Database pool exhausted", "description": "Too many connections"},
        {"id": "102", "key": "OPS-102", "summary": "Nginx 502 bad gateway", "description": "Upstream dead"},
    ])

    monkeypatch.setattr("opsmind.data.loader.load_jira_data", lambda: {"issues": mock_df})

    res = search_jira_issues("Nginx")
    assert len(res) == 1
    assert res[0]["key"] == "OPS-102"


def test_retrieval_handles_empty_or_varied_columns(monkeypatch):
    """B2 & B3 regression test: context retrieval handles comments and links schemas."""
    mock_incidents = pd.DataFrame([
        {"number": "INC0000001", "short_description": "Network flap", "description": "Switch offline"}
    ])
    mock_comments = pd.DataFrame([
        {"key": "OPS-102", "comment.author": "alice", "comment.body": "Restarted service"}
    ])
    mock_links = pd.DataFrame([
        {"inwardIssue.key": "OPS-101", "outwardIssue.key": "OPS-102", "type.name": "Relates", "type.inward": "relates to"}
    ])

    monkeypatch.setattr("opsmind.context.retrieval.load_incident_data", lambda: mock_incidents)
    monkeypatch.setattr("opsmind.context.retrieval.load_jira_data", lambda: {
        "issues": pd.DataFrame(),
        "comments": mock_comments,
        "changelog": pd.DataFrame(),
        "issuelinks": mock_links
    })

    ctx = FakeToolContext()
    res = asyncio.run(get_incident_context(ctx, query="Network"))

    assert res["status"] == "success"
    context = res.get("context", [])
    assert len(context) > 0

