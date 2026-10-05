"""Tests for Phase 4 — approval gate and runbook execution."""
import asyncio
import os
import sys
import types as _types

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
_cfg.logger = _logging.getLogger("test_approval")
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

# Now safe to import Phase 4 modules
from opsmind.tools.approval import (  # noqa: E402
    request_human_approval,
    approve_action,
    reject_action,
    get_pending_approvals,
    _next_approval_id,
)
from opsmind.tools.runbooks import (  # noqa: E402
    search_runbooks,
    get_runbook_steps,
    execute_runbook_step,
    _classify_step_risk,
    _load_runbooks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def ctx():
    return _FakeToolContext()


# ---------------------------------------------------------------------------
# _classify_step_risk — pure function
# ---------------------------------------------------------------------------

def test_classify_explicit_low():
    assert _classify_step_risk({"risk_tier": "LOW"}) == "LOW"


def test_classify_explicit_medium():
    assert _classify_step_risk({"risk_tier": "MEDIUM"}) == "MEDIUM"


def test_classify_explicit_high():
    assert _classify_step_risk({"risk_tier": "HIGH"}) == "HIGH"


def test_classify_heuristic_restart_is_medium():
    assert _classify_step_risk({"command": "systemctl restart myservice"}) == "MEDIUM"


def test_classify_heuristic_scale_is_high():
    assert _classify_step_risk({"command": "kubectl scale deployment app --replicas=5"}) == "HIGH"


def test_classify_heuristic_rollback_is_high():
    assert _classify_step_risk({"command": "kubectl rollout undo deployment/app"}) == "HIGH"


def test_classify_heuristic_curl_is_low():
    assert _classify_step_risk({"command": "curl -f http://host/health"}) == "LOW"


def test_classify_missing_fields_defaults_low():
    assert _classify_step_risk({}) == "LOW"


# ---------------------------------------------------------------------------
# Runbook loading
# ---------------------------------------------------------------------------

def test_runbooks_loaded():
    rbs = _load_runbooks()
    assert len(rbs) >= 5, f"Expected ≥5 runbooks, got {len(rbs)}: {list(rbs.keys())}"


def test_restart_service_runbook_exists():
    rbs = _load_runbooks()
    assert "restart_service" in rbs


def test_rollback_deployment_runbook_exists():
    rbs = _load_runbooks()
    assert "rollback_deployment" in rbs


def test_db_failover_runbook_exists():
    rbs = _load_runbooks()
    assert "db_failover" in rbs


# ---------------------------------------------------------------------------
# search_runbooks
# ---------------------------------------------------------------------------

def test_search_runbooks_by_name():
    c = ctx()
    result = run(search_runbooks(c, "restart"))
    assert result["total"] >= 1
    ids = [m["id"] for m in result["matches"]]
    assert "restart_service" in ids


def test_search_runbooks_by_keyword():
    c = ctx()
    result = run(search_runbooks(c, "rollback"))
    assert result["total"] >= 1


def test_search_runbooks_by_category():
    c = ctx()
    result = run(search_runbooks(c, "failover", category="database"))
    assert result["total"] >= 1


def test_search_runbooks_no_match():
    c = ctx()
    result = run(search_runbooks(c, "zzznomatch_xyz"))
    assert result["total"] == 0


def test_search_runbooks_returns_step_count():
    c = ctx()
    result = run(search_runbooks(c, "restart_service"))
    match = next(m for m in result["matches"] if m["id"] == "restart_service")
    assert match["step_count"] >= 1


# ---------------------------------------------------------------------------
# get_runbook_steps
# ---------------------------------------------------------------------------

def test_get_runbook_steps_restart_service():
    c = ctx()
    result = run(get_runbook_steps(c, "restart_service"))
    assert "steps" in result
    assert len(result["steps"]) >= 2


def test_get_runbook_steps_has_risk_tiers():
    c = ctx()
    result = run(get_runbook_steps(c, "restart_service"))
    for step in result["steps"]:
        assert step["risk_tier"] in ("LOW", "MEDIUM", "HIGH")


def test_get_runbook_steps_ordered():
    c = ctx()
    result = run(get_runbook_steps(c, "restart_service"))
    ids = [s["id"] for s in result["steps"]]
    assert ids[0] == "check_health"


def test_get_runbook_steps_high_risk_listed():
    c = ctx()
    result = run(get_runbook_steps(c, "scale_deployment"))
    assert len(result["high_risk_steps"]) >= 1


def test_get_runbook_steps_not_found():
    c = ctx()
    result = run(get_runbook_steps(c, "nonexistent_runbook"))
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# execute_runbook_step — dry-run
# ---------------------------------------------------------------------------

def test_dry_run_returns_simulated_output():
    """Roadmap: execute_runbook_step dry_run=True returns simulated output."""
    c = ctx()
    result = run(execute_runbook_step(c, "restart_service", "graceful_restart", dry_run=True))
    assert result["status"] == "success"
    assert result["dry_run"] is True
    assert "dry-run" in result["output"].lower() or "would" in result["output"].lower()


def test_dry_run_low_risk_no_approval():
    c = ctx()
    result = run(execute_runbook_step(c, "restart_service", "check_health", dry_run=True))
    assert result["status"] == "success"
    assert result["risk_tier"] == "LOW"


def test_dry_run_medium_risk_no_approval():
    c = ctx()
    result = run(execute_runbook_step(c, "restart_service", "graceful_restart", dry_run=True))
    assert result["status"] == "success"
    assert result["risk_tier"] == "MEDIUM"


def test_dry_run_high_risk_no_approval_needed():
    """dry_run=True bypasses approval even for HIGH-risk steps."""
    c = ctx()
    result = run(execute_runbook_step(c, "scale_deployment", "scale_up", dry_run=True))
    assert result["status"] == "success"
    assert result["dry_run"] is True


def test_execute_real_high_risk_without_approval_creates_pending():
    """Roadmap: HIGH-risk step without approval creates PENDING record."""
    c = ctx()
    result = run(execute_runbook_step(c, "scale_deployment", "scale_up", dry_run=False))
    assert result["status"] == "pending_approval"
    assert "approval_id" in result
    pending = c.state.get("pending_approvals", {})
    assert len(pending) >= 1
    record = list(pending.values())[0]
    assert record["status"] == "PENDING"
    assert record["risk_tier"] == "HIGH"


def test_execute_real_low_risk_skips_approval():
    """Roadmap: LOW-risk step skips approval."""
    c = ctx()
    result = run(execute_runbook_step(c, "restart_service", "check_health", dry_run=False))
    assert result["status"] == "success"
    assert c.state.get("pending_approvals", {}) == {}


def test_execute_step_not_found():
    c = ctx()
    result = run(execute_runbook_step(c, "restart_service", "nonexistent_step", dry_run=True))
    assert result["status"] == "error"


def test_execute_runbook_not_found():
    c = ctx()
    result = run(execute_runbook_step(c, "nonexistent_runbook", "step1", dry_run=True))
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# request_human_approval
# ---------------------------------------------------------------------------

def test_request_approval_creates_pending_record():
    """Roadmap: HIGH-risk step creates a pending approval record."""
    c = ctx()
    result = run(request_human_approval(c, "scale_up", "Scale to 10 replicas", "HIGH"))
    assert result["status"] == "PENDING"
    assert result["approval_id"].startswith("APR-")
    pending = c.state.get("pending_approvals", {})
    assert result["approval_id"] in pending
    assert pending[result["approval_id"]]["status"] == "PENDING"


def test_request_approval_increments_counter():
    c = ctx()
    r1 = run(request_human_approval(c, "action1", "desc1", "HIGH"))
    r2 = run(request_human_approval(c, "action2", "desc2", "HIGH"))
    assert r1["approval_id"] != r2["approval_id"]


def test_request_approval_stores_risk_tier():
    c = ctx()
    result = run(request_human_approval(c, "promote_replica", "Promote DB replica", "HIGH"))
    aid = result["approval_id"]
    record = c.state["pending_approvals"][aid]
    assert record["risk_tier"] == "HIGH"


def test_request_approval_stores_context_data():
    c = ctx()
    result = run(request_human_approval(
        c, "scale_up", "Scale deployment", "HIGH",
        context_data={"runbook_id": "scale_deployment", "step_id": "scale_up"}
    ))
    aid = result["approval_id"]
    record = c.state["pending_approvals"][aid]
    assert record["context_data"]["runbook_id"] == "scale_deployment"


# ---------------------------------------------------------------------------
# approve_action
# ---------------------------------------------------------------------------

def test_approve_action_clears_pending():
    """Roadmap: approve_action clears pending status."""
    c = ctx()
    req = run(request_human_approval(c, "graceful_restart", "Restart service", "MEDIUM"))
    aid = req["approval_id"]
    result = run(approve_action(c, aid))
    assert result["status"] == "APPROVED"
    assert c.state["pending_approvals"][aid]["status"] == "APPROVED"


def test_approve_action_not_found():
    c = ctx()
    result = run(approve_action(c, "APR-999999"))
    assert result["status"] == "error"


def test_approve_action_already_resolved():
    c = ctx()
    req = run(request_human_approval(c, "action", "desc", "HIGH"))
    aid = req["approval_id"]
    run(approve_action(c, aid))
    result = run(approve_action(c, aid))  # second approve
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# reject_action
# ---------------------------------------------------------------------------

def test_reject_action_blocks_execution():
    """Roadmap: reject_action blocks execution."""
    c = ctx()
    req = run(request_human_approval(c, "promote_replica", "Promote DB", "HIGH"))
    aid = req["approval_id"]
    result = run(reject_action(c, aid, reason="Not safe right now"))
    assert result["status"] == "rejected"
    assert c.state["pending_approvals"][aid]["status"] == "REJECTED"


def test_reject_action_stores_reason():
    c = ctx()
    req = run(request_human_approval(c, "scale_up", "Scale", "HIGH"))
    aid = req["approval_id"]
    run(reject_action(c, aid, reason="Too risky"))
    record = c.state["pending_approvals"][aid]
    assert record["rejection_reason"] == "Too risky"


def test_reject_action_not_found():
    c = ctx()
    result = run(reject_action(c, "APR-000000"))
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# get_pending_approvals
# ---------------------------------------------------------------------------

def test_get_pending_approvals_empty():
    c = ctx()
    result = run(get_pending_approvals(c))
    assert result["pending_count"] == 0
    assert result["pending"] == []


def test_get_pending_approvals_lists_pending():
    c = ctx()
    run(request_human_approval(c, "action1", "desc1", "HIGH"))
    run(request_human_approval(c, "action2", "desc2", "HIGH"))
    result = run(get_pending_approvals(c))
    assert result["pending_count"] == 2


def test_get_pending_approvals_excludes_resolved():
    c = ctx()
    req = run(request_human_approval(c, "action1", "desc1", "HIGH"))
    run(approve_action(c, req["approval_id"]))
    run(request_human_approval(c, "action2", "desc2", "HIGH"))
    result = run(get_pending_approvals(c))
    assert result["pending_count"] == 1
    assert result["total_count"] == 2


# ---------------------------------------------------------------------------
# Full approval flow integration
# ---------------------------------------------------------------------------

def test_high_risk_step_full_approval_flow():
    """
    Roadmap acceptance: HIGH-risk step → pending → approve → execute succeeds.
    """
    c = ctx()

    # Step 1: attempt real execution of HIGH-risk step → blocked
    result = run(execute_runbook_step(c, "scale_deployment", "scale_up", dry_run=False))
    assert result["status"] == "pending_approval"
    approval_id = result["approval_id"]

    # Step 2: approve
    approve_result = run(approve_action(c, approval_id))
    assert approve_result["status"] == "APPROVED"

    # Step 3: re-execute — now approved, should succeed
    result2 = run(execute_runbook_step(c, "scale_deployment", "scale_up", dry_run=False))
    assert result2["status"] == "success"


def test_high_risk_step_reject_flow():
    """
    Roadmap acceptance: HIGH-risk step → pending → reject → pipeline stops.
    """
    c = ctx()

    result = run(execute_runbook_step(c, "rollback_deployment", "rollback", dry_run=False))
    assert result["status"] == "pending_approval"
    approval_id = result["approval_id"]

    reject_result = run(reject_action(c, approval_id))
    assert reject_result["status"] == "rejected"

    # Approval is now REJECTED — a new attempt would create a new pending record
    pending = run(get_pending_approvals(c))
    assert pending["pending_count"] == 0  # rejected, not pending


def test_low_risk_step_skips_approval_real_exec():
    """Roadmap: LOW-risk step skips approval entirely."""
    c = ctx()
    result = run(execute_runbook_step(c, "restart_service", "check_health", dry_run=False))
    assert result["status"] == "success"
    assert c.state.get("pending_approvals", {}) == {}
