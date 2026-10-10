"""
Unit and integration tests for Jira write automation.
All tests use simulated mode or mocked connector; no real external calls.
"""

import asyncio
import os
import sys
import types as _types
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# ---------------------------------------------------------------------------
# Isolate from ADK and heavy import chain
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if "opsmind" not in sys.modules:
    _pkg = _types.ModuleType("opsmind")
    _pkg.__path__ = [os.path.join(_ROOT, "opsmind")]
    _pkg.__package__ = "opsmind"
    sys.modules["opsmind"] = _pkg

# Stub google.adk.tools.tool_context
_google = _types.ModuleType("google")
_google_adk = _types.ModuleType("google.adk")
_google_adk_tools = _types.ModuleType("google.adk.tools")
_google_adk_tools_tc = _types.ModuleType("google.adk.tools.tool_context")


class _FakeToolContext:
    def __init__(self):
        self.state: dict = {}


_google_adk_tools_tc.ToolContext = _FakeToolContext
sys.modules.setdefault("google", _google)
sys.modules.setdefault("google.adk", _google_adk)
sys.modules.setdefault("google.adk.tools", _google_adk_tools)
sys.modules.setdefault("google.adk.tools.tool_context", _google_adk_tools_tc)

# Stub opsmind.config
import logging as _logging
_cfg = _types.ModuleType("opsmind.config")
_cfg.logger = _logging.getLogger("test_jira_write")
_cfg.MODEL_NAME = "gemini-2.0-flash-001"
_cfg.OUTPUT_DIR = os.path.join(_ROOT, "output")
_cfg.GCP_STORAGE_ENABLED = False
_cfg.INCIDENT_DATA_PATH = os.path.join(_ROOT, "opsmind", "data", "incident_event_log.csv")
_cfg.JIRA_ISSUES_PATH = os.path.join(_ROOT, "opsmind", "data", "jira_issues.csv")
_cfg.JIRA_COMMENTS_PATH = os.path.join(_ROOT, "opsmind", "data", "jira_comments.csv")
_cfg.JIRA_CHANGELOG_PATH = os.path.join(_ROOT, "opsmind", "data", "jira_changelog.csv")
_cfg.JIRA_ISSUELINKS_PATH = os.path.join(_ROOT, "opsmind", "data", "jira_issuelinks.csv")
_cfg.get_jira_config = lambda: {
    "base_url": "",
    "username": "",
    "api_token": "",
    "project_keys": ["OPS"],
    "enabled": False,
}
sys.modules["opsmind.config"] = _cfg

# Stub opsmind.utils
_utils = _types.ModuleType("opsmind.utils")
_utils.validate_csv_file = lambda p: False
_utils.upload_file_to_gcp = lambda **kw: {"status": "error"}
_utils.generate_download_link = lambda **kw: {"status": "error"}
_utils.list_postmortem_files_in_gcp = lambda: {"status": "error"}
sys.modules.setdefault("opsmind.utils", _utils)

# Stub opsmind.tools.guardrail
_guardrail_mod = _types.ModuleType("opsmind.tools.guardrail")
_guardrail_mod.with_guardrail = lambda fn: fn
_tools_pkg = _types.ModuleType("opsmind.tools")
_tools_pkg.__path__ = [os.path.join(_ROOT, "opsmind", "tools")]
_tools_pkg.__package__ = "opsmind.tools"
sys.modules.setdefault("opsmind.tools", _tools_pkg)
sys.modules.setdefault("opsmind.tools.guardrail", _guardrail_mod)

from opsmind.tools.jira_write import (
    create_jira_ticket,
    add_jira_comment,
    transition_jira_issue,
    _is_jira_configured,
)
from opsmind.data.connectors.base import ConnectorConfig
from opsmind.data.connectors.jira import JiraConnector


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def tool_context():
    tc = _FakeToolContext()
    tc.state = {}
    return tc


def test_create_jira_ticket_simulated(tool_context):
    res = run(create_jira_ticket(
        tool_context=tool_context,
        summary="Database pool exhausted",
        description="P1 outage in order processing database",
        project_key="OPS",
        priority="Highest",
        simulate=True,
    ))

    assert res["status"] == "success"
    assert res["simulated"] is True
    assert res["key"].startswith("OPS-")
    assert "Database pool exhausted" in res["summary"]
    assert "url" in res


def test_add_jira_comment_simulated(tool_context):
    res = run(add_jira_comment(
        tool_context=tool_context,
        issue_key="OPS-10001",
        comment_body="Investigation started by SRE on-call.",
        simulate=True,
    ))

    assert res["status"] == "success"
    assert res["simulated"] is True
    assert res["issue_key"] == "OPS-10001"
    assert "comment_id" in res


def test_transition_jira_issue_simulated(tool_context):
    res = run(transition_jira_issue(
        tool_context=tool_context,
        issue_key="OPS-10001",
        target_status="In Progress",
        simulate=True,
    ))

    assert res["status"] == "success"
    assert res["simulated"] is True
    assert res["issue_key"] == "OPS-10001"
    assert res["target_status"] == "In Progress"


def test_is_jira_configured_detects_missing_or_placeholder():
    with patch("opsmind.tools.jira_write.get_jira_config") as mock_cfg:
        mock_cfg.return_value = {
            "base_url": "https://your-domain.atlassian.net",
            "username": "user@company.com",
            "api_token": "your-api-token",
        }
        assert _is_jira_configured() is False


def test_jira_connector_write_methods_mocked():
    config = ConnectorConfig(
        name="test_jira",
        connector_type="jira",
        connection_params={
            "base_url": "https://test.jira.com",
            "username": "test_user",
            "api_token": "test_token",
        }
    )
    connector = JiraConnector(config)

    mock_resp = AsyncMock()
    mock_resp.status = 201
    mock_resp.json = AsyncMock(return_value={"id": "999", "key": "OPS-999"})

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
    connector.session = mock_session

    issue = run(connector.create_issue(
        project_key="OPS",
        summary="Test Ticket",
        description="Test description",
    ))
    assert issue["key"] == "OPS-999"

    # Test comment
    comment_resp = AsyncMock()
    comment_resp.status = 201
    comment_resp.json = AsyncMock(return_value={"id": "1001", "body": "Comment text"})
    mock_session.post.return_value.__aenter__ = AsyncMock(return_value=comment_resp)

    comment = run(connector.add_comment(issue_key="OPS-999", body="Comment text"))
    assert comment["id"] == "1001"

    # Test transition
    trans_resp = AsyncMock()
    trans_resp.status = 204
    mock_session.post.return_value.__aenter__ = AsyncMock(return_value=trans_resp)

    trans = run(connector.transition_issue(issue_key="OPS-999", transition_name_or_id="5"))
    assert trans["status"] == "success"
