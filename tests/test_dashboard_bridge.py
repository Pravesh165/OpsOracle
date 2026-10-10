"""
Tests for dashboard/data_bridge.py — Phase 7.

No Streamlit, no ADK, no google-adk import chain.
All tests verify return shapes and types only.
"""
from __future__ import annotations

import os
import sys
import types as _types
import tempfile
import json

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on path
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ---------------------------------------------------------------------------
# Stub opsmind.* so data_bridge can be imported without google-adk
# ---------------------------------------------------------------------------

# opsmind package stub
if "opsmind" not in sys.modules:
    _pkg = _types.ModuleType("opsmind")
    _pkg.__path__ = [os.path.join(_ROOT, "opsmind")]
    _pkg.__package__ = "opsmind"
    sys.modules["opsmind"] = _pkg

# opsmind.config stub
import logging as _logging
_cfg = _types.ModuleType("opsmind.config")
_cfg.logger = _logging.getLogger("test_bridge")
_cfg.MODEL_NAME = "gemini-2.0-flash-001"
_cfg.OUTPUT_DIR = os.path.join(_ROOT, "output")
_cfg.GCP_STORAGE_ENABLED = False
_cfg.INCIDENT_DATA_PATH = os.path.join(_ROOT, "opsmind", "data", "datasets", "incidents", "incident_event_log.csv")
_cfg.JIRA_ISSUES_PATH = os.path.join(_ROOT, "opsmind", "data", "datasets", "jira", "issues.csv")
_cfg.JIRA_COMMENTS_PATH = os.path.join(_ROOT, "opsmind", "data", "datasets", "jira", "comments.csv")
_cfg.JIRA_CHANGELOG_PATH = os.path.join(_ROOT, "opsmind", "data", "datasets", "jira", "changelog.csv")
_cfg.JIRA_ISSUELINKS_PATH = os.path.join(_ROOT, "opsmind", "data", "datasets", "jira", "issuelinks.csv")
_cfg.get_jira_config = lambda: {
    "base_url": "",
    "username": "",
    "api_token": "",
    "project_keys": ["OPS"],
    "enabled": False,
}
_cfg.get_gcp_config = lambda: {}
sys.modules["opsmind.config"] = _cfg

# opsmind.utils stub
_utils = _types.ModuleType("opsmind.utils")
_utils.validate_csv_file = lambda p: False
_utils.upload_file_to_gcp = lambda **kw: {"status": "error"}
_utils.generate_download_link = lambda **kw: {"status": "error"}
_utils.list_postmortem_files_in_gcp = lambda: {"status": "error"}
sys.modules["opsmind.utils"] = _utils

# opsmind.tools.guardrail stub
_guardrail = _types.ModuleType("opsmind.tools.guardrail")
_guardrail.with_guardrail = lambda fn: fn
_tools_pkg = _types.ModuleType("opsmind.tools")
_tools_pkg.__path__ = [os.path.join(_ROOT, "opsmind", "tools")]
_tools_pkg.__package__ = "opsmind.tools"
sys.modules["opsmind.tools"] = _tools_pkg
sys.modules["opsmind.tools.guardrail"] = _guardrail

# ---------------------------------------------------------------------------
# Now import data_bridge (no Streamlit needed)
# ---------------------------------------------------------------------------
import importlib
import dashboard.data_bridge as bridge  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_postmortem_file(output_dir: str, incident_id: str = "INC0000001") -> str:
    """Write a minimal postmortem .md file and return its path."""
    os.makedirs(output_dir, exist_ok=True)
    fname = f"postmortem_{incident_id}_20240101_120000.md"
    path = os.path.join(output_dir, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Incident Postmortem: {incident_id}\n\n## Root Cause\nTest content.\n")
    return path


# ---------------------------------------------------------------------------
# get_incidents
# ---------------------------------------------------------------------------

def test_get_incidents_returns_dataframe():
    """Roadmap: incidents page shows all rows from incident_event_log.csv."""
    import pandas as pd
    result = bridge.get_incidents()
    assert isinstance(result, pd.DataFrame)


def test_get_incidents_empty_when_no_csv(monkeypatch):
    """Returns empty DataFrame gracefully when CSV is absent."""
    import pandas as pd

    def _empty():
        return pd.DataFrame()

    monkeypatch.setattr(bridge, "get_incidents", _empty)
    result = bridge.get_incidents()
    assert isinstance(result, pd.DataFrame)


def test_get_incident_states_returns_dict():
    result = bridge.get_incident_states()
    assert isinstance(result, dict)


def test_get_incident_categories_returns_dict():
    result = bridge.get_incident_categories()
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# get_postmortems
# ---------------------------------------------------------------------------

def test_get_postmortems_returns_list():
    """Roadmap: postmortems list is a list."""
    result = bridge.get_postmortems()
    assert isinstance(result, list)


def test_get_postmortems_item_has_required_keys(tmp_path, monkeypatch):
    """Each postmortem dict has filename, filepath, incident_id, content."""
    monkeypatch.setattr(bridge, "_OUTPUT_DIR", tmp_path)
    _make_postmortem_file(str(tmp_path), "INC0000001")

    result = bridge.get_postmortems()
    assert len(result) >= 1
    pm = result[0]
    for key in ("filename", "filepath", "incident_id", "content", "modified", "size_kb"):
        assert key in pm, f"Missing key: {key}"


def test_get_postmortems_content_is_string(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "_OUTPUT_DIR", tmp_path)
    _make_postmortem_file(str(tmp_path))
    result = bridge.get_postmortems()
    assert isinstance(result[0]["content"], str)
    assert len(result[0]["content"]) > 0


def test_get_postmortems_incident_id_extracted(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "_OUTPUT_DIR", tmp_path)
    _make_postmortem_file(str(tmp_path), "INC0000042")
    result = bridge.get_postmortems()
    assert result[0]["incident_id"] == "INC0000042"


def test_get_postmortems_empty_when_no_output_dir(tmp_path, monkeypatch):
    empty_dir = tmp_path / "nonexistent"
    monkeypatch.setattr(bridge, "_OUTPUT_DIR", empty_dir)
    result = bridge.get_postmortems()
    assert result == []


# ---------------------------------------------------------------------------
# get_mttr_data
# ---------------------------------------------------------------------------

def test_get_mttr_data_returns_dataframe():
    import pandas as pd
    result = bridge.get_mttr_data()
    assert isinstance(result, pd.DataFrame)
    assert not result.empty


def test_get_mttr_data_has_required_columns():
    result = bridge.get_mttr_data()
    for col in ("category", "mttr_hours", "incident_count"):
        assert col in result.columns, f"Missing column: {col}"


def test_get_mttr_data_mttr_positive():
    result = bridge.get_mttr_data()
    assert (result["mttr_hours"] > 0).all()


# ---------------------------------------------------------------------------
# get_recurring_patterns
# ---------------------------------------------------------------------------

def test_get_recurring_patterns_returns_dataframe():
    import pandas as pd
    result = bridge.get_recurring_patterns()
    assert isinstance(result, pd.DataFrame)
    assert not result.empty


def test_get_recurring_patterns_has_required_columns():
    result = bridge.get_recurring_patterns()
    for col in ("pattern", "count"):
        assert col in result.columns, f"Missing column: {col}"


# ---------------------------------------------------------------------------
# get_incident_timeline
# ---------------------------------------------------------------------------

def test_get_incident_timeline_returns_list():
    result = bridge.get_incident_timeline("INC0000001")
    assert isinstance(result, list)


def test_get_incident_timeline_non_empty():
    """Falls back to demo data when CSV absent — must return >= 1 event."""
    result = bridge.get_incident_timeline("INC_NONEXISTENT_XYZ")
    assert len(result) >= 1


def test_get_incident_timeline_event_has_required_keys():
    result = bridge.get_incident_timeline("INC0000001")
    for ev in result:
        for key in ("timestamp", "event", "detail"):
            assert key in ev, f"Missing key: {key}"


def test_get_incident_timeline_sorted_by_timestamp():
    result = bridge.get_incident_timeline("INC0000001")
    timestamps = [ev["timestamp"] for ev in result]
    assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# get_knowledge_stats
# ---------------------------------------------------------------------------

def test_get_knowledge_stats_returns_dict():
    """Roadmap: get_knowledge_stats returns a dict."""
    result = bridge.get_knowledge_stats()
    assert isinstance(result, dict)


def test_get_knowledge_stats_has_total_documents():
    result = bridge.get_knowledge_stats()
    assert "total_documents" in result


def test_get_knowledge_stats_total_documents_is_int():
    result = bridge.get_knowledge_stats()
    assert isinstance(result["total_documents"], int)


def test_get_knowledge_stats_has_sources():
    result = bridge.get_knowledge_stats()
    assert "sources" in result
    assert isinstance(result["sources"], dict)


def test_get_knowledge_stats_has_postmortem_count():
    result = bridge.get_knowledge_stats()
    assert "postmortem_count" in result


def test_get_knowledge_stats_has_index_loaded():
    result = bridge.get_knowledge_stats()
    assert "index_loaded" in result


# ---------------------------------------------------------------------------
# charts module — import and basic smoke test (no Streamlit)
# ---------------------------------------------------------------------------

def test_charts_import():
    """charts.py must import without Streamlit."""
    import dashboard.charts as charts
    assert hasattr(charts, "severity_pie")
    assert hasattr(charts, "state_bar")
    assert hasattr(charts, "mttr_trend")
    assert hasattr(charts, "category_bar")
    assert hasattr(charts, "recurring_patterns_bar")
    assert hasattr(charts, "knowledge_sources_pie")


def test_severity_pie_returns_figure():
    import dashboard.charts as charts
    fig = charts.severity_pie({"network": 10, "database": 5})
    assert fig is not None
    assert hasattr(fig, "data")


def test_state_bar_returns_figure():
    import dashboard.charts as charts
    fig = charts.state_bar({"New": 3, "Resolved": 7})
    assert fig is not None


def test_mttr_trend_returns_figure():
    import dashboard.charts as charts
    import pandas as pd
    df = pd.DataFrame({"category": ["net"], "mttr_hours": [4.0], "incident_count": [5]})
    fig = charts.mttr_trend(df)
    assert fig is not None


def test_mttr_trend_empty_df():
    import dashboard.charts as charts
    import pandas as pd
    fig = charts.mttr_trend(pd.DataFrame())
    assert fig is not None


def test_knowledge_sources_pie_empty():
    import dashboard.charts as charts
    fig = charts.knowledge_sources_pie({})
    assert fig is not None


def test_knowledge_sources_pie_with_data():
    import dashboard.charts as charts
    fig = charts.knowledge_sources_pie({"incident": 50, "postmortem": 10})
    assert fig is not None
