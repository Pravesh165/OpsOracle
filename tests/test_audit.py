"""
Unit and integration tests for Structured Audit Logging.
Verifies JSONL event generation, field completeness, secret redaction, and listing tool.
"""

import asyncio
import json
import os
import sys
import types as _types
import pytest
from unittest.mock import MagicMock

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
_cfg.logger = _logging.getLogger("test_audit")
_cfg.MODEL_NAME = "gemini-2.0-flash-001"
_cfg.OUTPUT_DIR = os.path.join(_ROOT, "output")
_cfg.GCP_STORAGE_ENABLED = False
_cfg.get_jira_config = lambda: {
    "base_url": "",
    "username": "",
    "api_token": "",
    "project_keys": ["OPS"],
    "enabled": False,
}
sys.modules.setdefault("opsmind.config", _cfg)

# Stub opsmind.tools.guardrail
_guardrail_mod = _types.ModuleType("opsmind.tools.guardrail")
_guardrail_mod.with_guardrail = lambda fn: fn
_tools_pkg = _types.ModuleType("opsmind.tools")
_tools_pkg.__path__ = [os.path.join(_ROOT, "opsmind", "tools")]
_tools_pkg.__package__ = "opsmind.tools"
sys.modules.setdefault("opsmind.tools", _tools_pkg)
sys.modules.setdefault("opsmind.tools.guardrail", _guardrail_mod)

from opsmind.audit.logger import AuditLogger, sanitize_value, REDACTED_PLACEHOLDER
from opsmind.audit.decorator import audit_action
from opsmind.tools.audit_tools import list_audit_events
from opsmind.tools.triage import triage_incident


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def clean_audit_logger(tmp_path):
    log_file = tmp_path / "audit_test.jsonl"
    AuditLogger.reset_instance()
    logger = AuditLogger.get_instance(str(log_file))
    yield logger
    AuditLogger.reset_instance()


@pytest.fixture
def tool_context():
    tc = _FakeToolContext()
    tc.state = {"session_id": "test_sess_42"}
    return tc


def test_sanitize_value_masks_secrets():
    payload = {
        "user": "alice",
        "api_token": "secret_abc123",
        "nested": {
            "password": "super_secret_pw",
            "bearer_header": "Bearer eyJhbGciOi...",
            "normal_field": "public_info",
        },
        "items": [
            {"access_token": "token_val", "name": "service1"}
        ]
    }

    cleaned = sanitize_value(payload)

    assert cleaned["user"] == "alice"
    assert cleaned["api_token"] == REDACTED_PLACEHOLDER
    assert cleaned["nested"]["password"] == REDACTED_PLACEHOLDER
    assert "[REDACTED]" in cleaned["nested"]["bearer_header"]
    assert cleaned["nested"]["normal_field"] == "public_info"
    assert cleaned["items"][0]["access_token"] == REDACTED_PLACEHOLDER
    assert cleaned["items"][0]["name"] == "service1"


def test_audit_logger_records_event(clean_audit_logger):
    event = clean_audit_logger.log_event(
        action="test_action",
        tool="test_tool",
        args_summary={"arg1": "val1", "secret_key": "pass123"},
        result_code="success",
        duration_ms=45.2,
        session_id="sess_100",
    )

    assert event["action"] == "test_action"
    assert event["tool"] == "test_tool"
    assert event["session_id"] == "sess_100"
    assert event["result_code"] == "success"
    assert event["duration_ms"] == 45.2
    assert "timestamp" in event
    assert event["args_summary"]["secret_key"] == REDACTED_PLACEHOLDER

    # Check file contents
    assert clean_audit_logger.log_file.exists()
    with open(clean_audit_logger.log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["tool"] == "test_tool"


def test_audit_action_decorator_on_async_function(clean_audit_logger, tool_context):
    @audit_action("custom_operation", tool_name="custom_async_tool")
    async def sample_tool(tool_context, param_x: str, secret_token: str = "hide_me"):
        return {"status": "success", "echo": param_x}

    res = run(sample_tool(tool_context, param_x="hello_world", secret_token="very_secret"))
    assert res["status"] == "success"

    events = clean_audit_logger.query_events(tool="custom_async_tool")
    assert len(events) == 1
    ev = events[0]
    assert ev["action"] == "custom_operation"
    assert ev["tool"] == "custom_async_tool"
    assert ev["session_id"] == "test_sess_42"
    assert ev["result_code"] == "success"
    assert ev["duration_ms"] >= 0
    assert ev["args_summary"]["param_x"] == "hello_world"
    assert ev["args_summary"]["secret_token"] == REDACTED_PLACEHOLDER


def test_list_audit_events_tool(clean_audit_logger, tool_context):
    clean_audit_logger.log_event("act_a", "tool_a", {}, "success", 10.0, "sess_1")
    clean_audit_logger.log_event("act_b", "tool_b", {}, "success", 20.0, "sess_1")

    res = run(list_audit_events(tool_context, limit=10))
    assert res["status"] == "success"
    assert res["count"] >= 2


def test_triage_p1_creates_jira_and_audits(clean_audit_logger, tool_context):
    p1_incident = {
        "number": "INC9999999",
        "priority": "P1",
        "category": "network",
        "symptom": "Major backbone switch failure, critical traffic dropped",
    }

    triage_res = run(triage_incident(tool_context, p1_incident))

    assert triage_res["priority_normalised"] == "P1"
    assert "jira_ticket" in triage_res
    assert triage_res["jira_ticket"]["status"] == "success"
    assert triage_res["jira_ticket"]["key"].startswith("OPS-")

    # Audit events should capture both triage and auto Jira creation
    events = clean_audit_logger.query_events()
    tools_called = [e["tool"] for e in events]
    assert "triage_incident" in tools_called
    assert "create_jira_ticket" in tools_called

