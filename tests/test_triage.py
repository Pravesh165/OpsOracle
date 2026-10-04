"""Tests for opsmind/tools/triage.py — Phase 2."""
import asyncio
import os
import sys
import types as _types

import pytest

# ---------------------------------------------------------------------------
# Isolate from ADK import chain (same pattern as test_retrieval.py)
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if "opsmind" not in sys.modules:
    _pkg = _types.ModuleType("opsmind")
    _pkg.__path__ = [os.path.join(_ROOT, "opsmind")]
    _pkg.__package__ = "opsmind"
    sys.modules["opsmind"] = _pkg

# Stub heavy sub-packages that pull in google-adk
for _mod in [
    "opsmind.core",
    "opsmind.core.agents",
    "opsmind.context",
]:
    if _mod not in sys.modules:
        _m = _types.ModuleType(_mod)
        sys.modules[_mod] = _m

# Stub google.adk.tools.tool_context so triage.py can import it
import types as _t
_google = _t.ModuleType("google")
_google_adk = _t.ModuleType("google.adk")
_google_adk_tools = _t.ModuleType("google.adk.tools")
_google_adk_tools_tc = _t.ModuleType("google.adk.tools.tool_context")


class _FakeToolContext:
    def __init__(self):
        self.state: dict = {}


_google_adk_tools_tc.ToolContext = _FakeToolContext
sys.modules.setdefault("google", _google)
sys.modules.setdefault("google.adk", _google_adk)
sys.modules.setdefault("google.adk.tools", _google_adk_tools)
sys.modules.setdefault("google.adk.tools.tool_context", _google_adk_tools_tc)

# Stub opsmind.config.logger
import logging as _logging
_cfg_mod = _t.ModuleType("opsmind.config")
_cfg_mod.logger = _logging.getLogger("test_triage")
_cfg_mod.MODEL_NAME = "gemini-2.0-flash-001"
sys.modules["opsmind.config"] = _cfg_mod

# Stub opsmind.tools.guardrail — make with_guardrail a no-op pass-through
_guardrail_mod = _t.ModuleType("opsmind.tools.guardrail")


def _passthrough(fn):
    return fn


_guardrail_mod.with_guardrail = _passthrough

# opsmind.tools must be a package (has __path__) so sub-module imports work
_tools_pkg = _t.ModuleType("opsmind.tools")
_tools_pkg.__path__ = [os.path.join(_ROOT, "opsmind", "tools")]
_tools_pkg.__package__ = "opsmind.tools"
sys.modules["opsmind.tools"] = _tools_pkg
sys.modules["opsmind.tools.guardrail"] = _guardrail_mod

# Now safe to import triage
from opsmind.tools.triage import (  # noqa: E402
    _severity_score,
    _normalise_priority,
    _route_team,
    _urgency_label,
    _impact_label,
    _VALID_TRANSITIONS,
    triage_incident,
    get_triage_status,
    transition_incident_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def ctx():
    return _FakeToolContext()


# ---------------------------------------------------------------------------
# _severity_score — pure function tests
# ---------------------------------------------------------------------------

def test_p1_network_is_critical():
    score = _severity_score("P1", "network")
    assert score == 1.0


def test_p1_database_near_critical():
    score = _severity_score("P1", "database")
    assert score >= 0.9


def test_p1_security_is_critical():
    score = _severity_score("P1", "security")
    assert score == 1.0


def test_p2_network_high():
    score = _severity_score("P2", "network")
    assert 0.6 <= score < 0.9


def test_p3_software_low():
    score = _severity_score("P3", "software")
    assert score < 0.5


def test_outage_keyword_boosts_severity():
    base = _severity_score("P2", "network")
    boosted = _severity_score("P2", "network", "site outage detected")
    assert boosted > base
    assert boosted - base == pytest.approx(0.20, abs=0.01)


def test_data_loss_keyword_boosts_severity():
    base = _severity_score("P2", "database")
    boosted = _severity_score("P2", "database", "data loss in production")
    assert boosted > base
    assert boosted - base >= 0.30


def test_customer_keyword_boosts_severity():
    base = _severity_score("P2", "software")
    boosted = _severity_score("P2", "software", "customer facing outage")
    assert boosted > base


def test_severity_capped_at_1():
    score = _severity_score("P1", "security", "outage data loss breach customer production")
    assert score <= 1.0


def test_unknown_category_uses_priority_fallback():
    score = _severity_score("P1", "unknown_category")
    assert score > 0.5  # P1 fallback is 0.75


def test_normalise_priority_variants():
    assert _normalise_priority("1") == "P1"
    assert _normalise_priority("critical") == "P1"
    assert _normalise_priority("high") == "P2"
    assert _normalise_priority("medium") == "P3"
    assert _normalise_priority("low") == "P4"
    assert _normalise_priority("P2") == "P2"


# ---------------------------------------------------------------------------
# _route_team
# ---------------------------------------------------------------------------

def test_route_network_team():
    assert _route_team("network") == "network-ops"


def test_route_database_team():
    assert _route_team("database") == "database-ops"


def test_route_security_team():
    assert _route_team("security") == "security-ops"


def test_route_unknown_fallback():
    assert _route_team("unknown") == "ops-team"


# ---------------------------------------------------------------------------
# _urgency_label / _impact_label
# ---------------------------------------------------------------------------

def test_urgency_critical():
    assert _urgency_label(0.95) == "CRITICAL"


def test_urgency_high():
    assert _urgency_label(0.75) == "HIGH"


def test_urgency_medium():
    assert _urgency_label(0.50) == "MEDIUM"


def test_urgency_low():
    assert _urgency_label(0.20) == "LOW"


def test_impact_enterprise():
    assert _impact_label(0.95) == "enterprise-wide"


def test_impact_individual():
    assert _impact_label(0.10) == "individual"


# ---------------------------------------------------------------------------
# triage_incident — async tool
# ---------------------------------------------------------------------------

def test_triage_returns_required_fields():
    c = ctx()
    result = run(triage_incident(c, {"priority": "P1", "category": "network", "symptom": "site outage"}))
    for field in ["incident_id", "severity", "urgency", "impact", "affected_service",
                  "suggested_team", "routing_reason", "state"]:
        assert field in result, f"Missing field: {field}"


def test_triage_p1_network_outage_critical():
    c = ctx()
    result = run(triage_incident(c, {"priority": "P1", "category": "network", "symptom": "site outage"}))
    assert result["severity"] >= 0.9
    assert result["suggested_team"] == "network-ops"
    assert result["urgency"] == "CRITICAL"


def test_triage_stores_in_session_state():
    c = ctx()
    result = run(triage_incident(c, {"number": "INC001", "priority": "P2", "category": "database"}))
    assert "INC001" in c.state.get("incident_states", {})


def test_triage_state_is_triaged():
    c = ctx()
    result = run(triage_incident(c, {"number": "INC002", "priority": "P3", "category": "software"}))
    assert result["state"] == "TRIAGED"


def test_triage_affected_service_from_cmdb_ci():
    c = ctx()
    result = run(triage_incident(c, {
        "priority": "P1", "category": "database",
        "cmdb_ci": "prod-db-01",
    }))
    assert result["affected_service"] == "prod-db-01"


# ---------------------------------------------------------------------------
# get_triage_status
# ---------------------------------------------------------------------------

def test_get_triage_status_found():
    c = ctx()
    run(triage_incident(c, {"number": "INC003", "priority": "P1", "category": "security"}))
    status = run(get_triage_status(c, "INC003"))
    assert status["found"] is True
    assert status["triage"]["incident_id"] == "INC003"


def test_get_triage_status_not_found():
    c = ctx()
    status = run(get_triage_status(c, "NONEXISTENT"))
    assert status["found"] is False


# ---------------------------------------------------------------------------
# transition_incident_state — state machine
# ---------------------------------------------------------------------------

def test_state_transition_detected_to_triaged():
    c = ctx()
    result = run(transition_incident_state(c, "INC010", "TRIAGED"))
    assert result["new_state"] == "TRIAGED"
    assert result["previous_state"] == "DETECTED"


def test_state_transition_triaged_to_acknowledged():
    c = ctx()
    run(transition_incident_state(c, "INC011", "TRIAGED"))
    result = run(transition_incident_state(c, "INC011", "ACKNOWLEDGED"))
    assert result["new_state"] == "ACKNOWLEDGED"


def test_state_transition_to_escalated():
    c = ctx()
    run(transition_incident_state(c, "INC012", "TRIAGED"))
    result = run(transition_incident_state(c, "INC012", "ESCALATED"))
    assert result["new_state"] == "ESCALATED"


def test_state_transition_invalid_raises():
    c = ctx()
    with pytest.raises(ValueError, match="Invalid transition"):
        run(transition_incident_state(c, "INC013", "RESOLVED"))  # DETECTED → RESOLVED invalid


def test_state_transition_closed_has_no_exits():
    c = ctx()
    # Walk to CLOSED
    for state in ["TRIAGED", "ACKNOWLEDGED", "MITIGATING", "RESOLVED", "CLOSED"]:
        run(transition_incident_state(c, "INC014", state))
    with pytest.raises(ValueError):
        run(transition_incident_state(c, "INC014", "RESOLVED"))


def test_state_history_recorded():
    c = ctx()
    run(transition_incident_state(c, "INC015", "TRIAGED"))
    run(transition_incident_state(c, "INC015", "ACKNOWLEDGED"))
    record = c.state["incident_states"]["INC015"]
    assert len(record["state_history"]) >= 2


def test_triage_then_transition_full_flow():
    """Triage an incident then walk it through to RESOLVED."""
    c = ctx()
    triage_result = run(triage_incident(c, {
        "number": "INC020",
        "priority": "P1",
        "category": "network",
        "symptom": "outage",
    }))
    assert triage_result["state"] == "TRIAGED"

    run(transition_incident_state(c, "INC020", "ACKNOWLEDGED"))
    run(transition_incident_state(c, "INC020", "MITIGATING"))
    run(transition_incident_state(c, "INC020", "RESOLVED"))

    status = run(get_triage_status(c, "INC020"))
    assert status["triage"]["state"] == "RESOLVED"
