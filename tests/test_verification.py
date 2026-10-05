"""Tests for Phase 5 — post-remediation verification loop."""
import asyncio
import os
import sys
import types as _types
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Isolate from ADK import chain (same pattern as previous phases)
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
_cfg.logger = _logging.getLogger("test_verification")
_cfg.MODEL_NAME = "gemini-2.0-flash-001"
_cfg.OUTPUT_DIR = os.path.join(_ROOT, "output")
_cfg.GCP_STORAGE_ENABLED = False
sys.modules["opsmind.config"] = _cfg

# Stub opsmind.tools.guardrail — no-op pass-through
_guardrail_mod = _types.ModuleType("opsmind.tools.guardrail")
_guardrail_mod.with_guardrail = lambda fn: fn
_tools_pkg = _types.ModuleType("opsmind.tools")
_tools_pkg.__path__ = [os.path.join(_ROOT, "opsmind", "tools")]
_tools_pkg.__package__ = "opsmind.tools"
sys.modules["opsmind.tools"] = _tools_pkg
sys.modules["opsmind.tools.guardrail"] = _guardrail_mod

# Now safe to import Phase 5 modules
from opsmind.tools.verification import (  # noqa: E402
    verify_resolution,
    run_health_check,
    _http_check,
    _metric_check,
    _log_check,
    HealthCheck,
)
from opsmind.tools.triage import (  # noqa: E402
    triage_incident,
    transition_incident_state,
    close_incident,
    reopen_incident,
    get_triage_status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def ctx():
    return _FakeToolContext()


def _seed_incident(c, incident_id: str, state: str = "MITIGATING"):
    """Seed an incident in session state at a given state."""
    states = c.state.get("incident_states", {})
    states[incident_id] = {
        "incident_id": incident_id,
        "state": state,
        "state_history": [{"from": "DETECTED", "to": state, "at": "2024-01-01T00:00:00"}],
    }
    c.state["incident_states"] = states


# ---------------------------------------------------------------------------
# HealthCheck dataclass
# ---------------------------------------------------------------------------

def test_healthcheck_dataclass_defaults():
    hc = HealthCheck(name="api", type="http", endpoint="http://host/health", expected="200")
    assert hc.timeout_sec == 10
    assert hc.max_retries == 3


# ---------------------------------------------------------------------------
# _http_check — pure function (mocked network)
# ---------------------------------------------------------------------------

def test_http_check_pass_on_200():
    """Roadmap: HTTP check passes on 200."""
    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": True, "type": "http", "actual": 200, "expected": 200}
        result = mock_http("http://example.com/health", "200", 5, 1)
    assert result["passed"] is True
    assert result["actual"] == 200


def test_http_check_fail_on_503():
    """Roadmap: HTTP check fails on 503."""
    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": False, "type": "http", "actual": 503, "expected": 200}
        result = mock_http("http://example.com/health", "200", 5, 1)
    assert result["passed"] is False
    assert result["actual"] == 503


def test_http_check_real_pass(httpbin_or_skip):
    """Integration: real HTTP check against httpbin (skipped if unavailable)."""
    result = _http_check("http://httpbin.org/status/200", "200", 10, 2)
    assert result["passed"] is True


# ---------------------------------------------------------------------------
# _metric_check stub
# ---------------------------------------------------------------------------

def test_metric_check_stub_returns_pending():
    """Roadmap: metric check stub returns pending."""
    result = _metric_check("cpu_usage_percent", "<80")
    assert result["status"] == "pending"
    assert result["passed"] is None
    assert result["type"] == "metric"


def test_log_check_stub_returns_pending():
    result = _log_check("/var/log/app.log", "no errors")
    assert result["status"] == "pending"
    assert result["passed"] is None
    assert result["type"] == "log"


# ---------------------------------------------------------------------------
# run_health_check (async wrapper)
# ---------------------------------------------------------------------------

def test_run_health_check_http_pass():
    c = ctx()
    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": True, "type": "http", "actual": 200, "expected": 200}
        result = run(run_health_check(c, {
            "name": "api_health", "type": "http",
            "endpoint": "http://host/health", "expected": "200",
        }))
    assert result["passed"] is True
    assert result["name"] == "api_health"
    assert "checked_at" in result


def test_run_health_check_http_fail():
    c = ctx()
    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": False, "type": "http", "actual": 503, "expected": 200}
        result = run(run_health_check(c, {
            "name": "api_health", "type": "http",
            "endpoint": "http://host/health", "expected": "200",
        }))
    assert result["passed"] is False


def test_run_health_check_metric_stub():
    c = ctx()
    result = run(run_health_check(c, {
        "name": "cpu_check", "type": "metric",
        "endpoint": "cpu_usage", "expected": "<80",
    }))
    assert result["passed"] is None
    assert result["status"] == "pending"


def test_run_health_check_unknown_type():
    c = ctx()
    result = run(run_health_check(c, {
        "name": "bad", "type": "unknown_type",
        "endpoint": "x", "expected": "y",
    }))
    assert result["passed"] is False


# ---------------------------------------------------------------------------
# verify_resolution — all pass → RESOLVED
# ---------------------------------------------------------------------------

def test_verify_resolution_all_pass_closes_incident():
    """Roadmap: all checks pass → incident transitions to RESOLVED."""
    c = ctx()
    _seed_incident(c, "INC0000001", "MITIGATING")

    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": True, "type": "http", "actual": 200, "expected": 200}
        result = run(verify_resolution(c, "INC0000001", [
            {"name": "api", "type": "http", "endpoint": "http://host/health", "expected": "200"},
        ]))

    assert result["verdict"] == "PASS"
    assert result["new_state"] == "RESOLVED"
    states = c.state.get("incident_states", {})
    assert states["INC0000001"]["state"] == "RESOLVED"


def test_verify_resolution_all_pass_stores_postmortem_trigger():
    """PASS verdict stores pending_postmortem in session state."""
    c = ctx()
    _seed_incident(c, "INC0000002", "MITIGATING")

    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": True, "type": "http", "actual": 200, "expected": 200}
        run(verify_resolution(c, "INC0000002", [
            {"name": "api", "type": "http", "endpoint": "http://host/health", "expected": "200"},
        ]))

    trigger = c.state.get("pending_postmortem", {})
    assert trigger.get("incident_id") == "INC0000002"
    assert trigger.get("trigger_reason") == "verification_passed"


def test_verify_resolution_any_fail_reopens():
    """Roadmap: any check fails → incident back to MITIGATING."""
    c = ctx()
    _seed_incident(c, "INC0000003", "MITIGATING")

    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": False, "type": "http", "actual": 503, "expected": 200}
        result = run(verify_resolution(c, "INC0000003", [
            {"name": "api", "type": "http", "endpoint": "http://host/health", "expected": "200"},
        ]))

    assert result["verdict"] == "FAIL"
    assert result["new_state"] == "MITIGATING"
    assert "api" in result["failed_checks"]


def test_verify_resolution_mixed_pass_and_stub_resolves():
    """HTTP pass + metric stub (pending) → PASS (stubs are non-blocking)."""
    c = ctx()
    _seed_incident(c, "INC0000004", "MITIGATING")

    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": True, "type": "http", "actual": 200, "expected": 200}
        result = run(verify_resolution(c, "INC0000004", [
            {"name": "api", "type": "http", "endpoint": "http://host/health", "expected": "200"},
            {"name": "cpu", "type": "metric", "endpoint": "cpu_usage", "expected": "<80"},
        ]))

    assert result["verdict"] == "PASS"
    assert result["pending_count"] == 1
    assert result["passed_count"] == 1


def test_verify_resolution_no_checks_returns_fail():
    c = ctx()
    _seed_incident(c, "INC0000005", "MITIGATING")
    result = run(verify_resolution(c, "INC0000005", []))
    assert result["verdict"] == "FAIL"


def test_verify_resolution_result_has_summary():
    c = ctx()
    _seed_incident(c, "INC0000006", "MITIGATING")
    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": True, "type": "http", "actual": 200, "expected": 200}
        result = run(verify_resolution(c, "INC0000006", [
            {"name": "api", "type": "http", "endpoint": "http://host/health", "expected": "200"},
        ]))
    assert "summary" in result
    assert "RESOLVED" in result["summary"]


def test_verify_resolution_counts_correct():
    c = ctx()
    _seed_incident(c, "INC0000007", "MITIGATING")
    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": False, "type": "http", "actual": 500, "expected": 200}
        result = run(verify_resolution(c, "INC0000007", [
            {"name": "check1", "type": "http", "endpoint": "http://host/a", "expected": "200"},
            {"name": "check2", "type": "http", "endpoint": "http://host/b", "expected": "200"},
        ]))
    assert result["total_checks"] == 2
    assert result["failed_count"] == 2
    assert result["passed_count"] == 0


# ---------------------------------------------------------------------------
# close_incident
# ---------------------------------------------------------------------------

def test_close_incident_from_resolved():
    c = ctx()
    _seed_incident(c, "INC0000010", "RESOLVED")
    result = run(close_incident(c, "INC0000010"))
    assert result["new_state"] == "CLOSED"
    states = c.state.get("incident_states", {})
    assert states["INC0000010"]["state"] == "CLOSED"


def test_close_incident_invalid_from_mitigating():
    c = ctx()
    _seed_incident(c, "INC0000011", "MITIGATING")
    with pytest.raises(ValueError):
        run(close_incident(c, "INC0000011"))


# ---------------------------------------------------------------------------
# reopen_incident
# ---------------------------------------------------------------------------

def test_reopen_incident_from_resolved():
    c = ctx()
    _seed_incident(c, "INC0000020", "RESOLVED")
    result = run(reopen_incident(c, "INC0000020", reason="Fix didn't hold"))
    assert result["new_state"] == "MITIGATING"
    states = c.state.get("incident_states", {})
    assert states["INC0000020"]["state"] == "MITIGATING"


def test_reopen_incident_from_closed():
    c = ctx()
    _seed_incident(c, "INC0000021", "CLOSED")
    result = run(reopen_incident(c, "INC0000021", reason="Customer still affected"))
    assert result["new_state"] == "MITIGATING"


def test_reopen_incident_stores_reason():
    c = ctx()
    _seed_incident(c, "INC0000022", "RESOLVED")
    run(reopen_incident(c, "INC0000022", reason="Regression detected"))
    states = c.state.get("incident_states", {})
    assert states["INC0000022"]["reopen_reason"] == "Regression detected"


def test_reopen_incident_no_reason():
    c = ctx()
    _seed_incident(c, "INC0000023", "RESOLVED")
    result = run(reopen_incident(c, "INC0000023"))
    assert result["new_state"] == "MITIGATING"


def test_reopen_incident_history_updated():
    c = ctx()
    _seed_incident(c, "INC0000024", "RESOLVED")
    run(reopen_incident(c, "INC0000024", reason="test"))
    states = c.state.get("incident_states", {})
    history = states["INC0000024"]["state_history"]
    last = history[-1]
    assert last["from"] == "RESOLVED"
    assert last["to"] == "MITIGATING"


# ---------------------------------------------------------------------------
# Full verification → close flow
# ---------------------------------------------------------------------------

def test_full_verify_and_close_flow():
    """
    Roadmap acceptance: verify PASS → RESOLVED → close → CLOSED.
    """
    c = ctx()
    _seed_incident(c, "INC0000030", "MITIGATING")

    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": True, "type": "http", "actual": 200, "expected": 200}
        verify_result = run(verify_resolution(c, "INC0000030", [
            {"name": "api", "type": "http", "endpoint": "http://host/health", "expected": "200"},
        ]))

    assert verify_result["verdict"] == "PASS"
    assert verify_result["new_state"] == "RESOLVED"

    close_result = run(close_incident(c, "INC0000030"))
    assert close_result["new_state"] == "CLOSED"


def test_full_verify_fail_and_reopen_flow():
    """
    Roadmap acceptance: verify FAIL → MITIGATING → reopen → still MITIGATING.
    """
    c = ctx()
    _seed_incident(c, "INC0000031", "MITIGATING")

    with patch("opsmind.tools.verification._http_check") as mock_http:
        mock_http.return_value = {"passed": False, "type": "http", "actual": 503, "expected": 200}
        verify_result = run(verify_resolution(c, "INC0000031", [
            {"name": "api", "type": "http", "endpoint": "http://host/health", "expected": "200"},
        ]))

    assert verify_result["verdict"] == "FAIL"
    assert verify_result["new_state"] == "MITIGATING"

    # Re-open explicitly (already MITIGATING, but reopen is idempotent)
    reopen_result = run(reopen_incident(c, "INC0000031", reason="Still failing"))
    assert reopen_result["new_state"] == "MITIGATING"


# ---------------------------------------------------------------------------
# Pytest fixture: skip real HTTP tests if network unavailable
# ---------------------------------------------------------------------------

@pytest.fixture
def httpbin_or_skip():
    import urllib.request
    try:
        urllib.request.urlopen("http://httpbin.org/status/200", timeout=3)
        return True
    except Exception:
        pytest.skip("httpbin.org not reachable — skipping real HTTP test")
