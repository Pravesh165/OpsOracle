"""
Runbook tools for OpsMind — Phase 4.

Loads YAML runbooks from opsmind/data/datasets/runbooks/.
All execution is dry-run by default; real execution is disabled.
HIGH-risk steps require human approval before proceeding.
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.adk.tools.tool_context import ToolContext

from opsmind.config import logger
from opsmind.tools.guardrail import with_guardrail

# ---------------------------------------------------------------------------
# YAML loading (lazy, cached per process)
# ---------------------------------------------------------------------------

_RUNBOOKS_DIR = Path(__file__).parent.parent / "data" / "datasets" / "runbooks"
_runbook_cache: Dict[str, Dict[str, Any]] = {}


def _load_runbooks() -> Dict[str, Dict[str, Any]]:
    """Load all YAML runbooks from disk into cache."""
    global _runbook_cache
    if _runbook_cache:
        return _runbook_cache

    try:
        import yaml
    except ImportError:
        logger.warning("pyyaml not installed; runbooks unavailable. Run: pip install pyyaml")
        return {}

    if not _RUNBOOKS_DIR.exists():
        logger.warning("Runbooks directory not found: %s", _RUNBOOKS_DIR)
        return {}

    for yaml_file in _RUNBOOKS_DIR.glob("*.yaml"):
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                rb = yaml.safe_load(f)
            if rb and rb.get("id"):
                _runbook_cache[rb["id"]] = rb
                logger.debug("Loaded runbook: %s", rb["id"])
        except Exception as exc:
            logger.warning("Failed to load runbook %s: %s", yaml_file, exc)

    logger.info("Loaded %d runbooks from %s", len(_runbook_cache), _RUNBOOKS_DIR)
    return _runbook_cache


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _classify_step_risk(step: Dict[str, Any]) -> str:
    """
    Return the risk tier for a runbook step.

    Uses the explicit 'risk_tier' field; falls back to keyword heuristics.
    """
    explicit = str(step.get("risk_tier", "")).upper()
    if explicit in _RISK_ORDER:
        return explicit

    # Heuristic fallback based on command keywords
    cmd = str(step.get("command", "")).lower()
    high_keywords = ["delete", "drop", "terminate", "promote", "undo", "rollback",
                     "scale", "failover", "flush", "truncate", "rm -rf"]
    medium_keywords = ["restart", "reload", "stop", "start", "deploy", "update",
                       "patch", "migrate", "del "]
    for kw in high_keywords:
        if kw in cmd:
            return "HIGH"
    for kw in medium_keywords:
        if kw in cmd:
            return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

@with_guardrail
async def search_runbooks(
    tool_context: ToolContext,
    query: str,
    category: str = "",
) -> Dict[str, Any]:
    """
    Search runbooks by name, id, description, or trigger keywords.

    Args:
        query:    Free-text search string.
        category: Optional incident category filter (e.g. "database").

    Returns:
        Dict with list of matching runbook summaries.
    """
    runbooks = _load_runbooks()
    query_lower = query.lower()
    cat_lower = category.lower()

    matches = []
    for rb_id, rb in runbooks.items():
        # Score: id/name/description match
        score = 0
        if query_lower in rb_id.lower():
            score += 3
        if query_lower in rb.get("name", "").lower():
            score += 3
        if query_lower in rb.get("description", "").lower():
            score += 2

        # Trigger keyword match
        for cond in rb.get("trigger_conditions", []):
            if isinstance(cond, dict):
                kws = cond.get("keywords", [])
                for kw in kws:
                    if query_lower in str(kw).lower():
                        score += 2
                if cat_lower and cond.get("category", "").lower() == cat_lower:
                    score += 2

        if score > 0:
            matches.append({
                "id": rb_id,
                "name": rb.get("name", rb_id),
                "description": rb.get("description", ""),
                "step_count": len(rb.get("steps", [])),
                "score": score,
            })

    matches.sort(key=lambda x: x["score"], reverse=True)

    return {
        "query": query,
        "matches": matches,
        "total": len(matches),
        "message": f"Found {len(matches)} runbook(s) matching '{query}'.",
    }


@with_guardrail
async def get_runbook_steps(
    tool_context: ToolContext,
    runbook_id: str,
) -> Dict[str, Any]:
    """
    Return the ordered steps for a runbook, with risk classification.

    Args:
        runbook_id: The runbook identifier (e.g. "restart_service").

    Returns:
        Dict with runbook metadata and annotated steps list.
    """
    runbooks = _load_runbooks()
    if runbook_id not in runbooks:
        return {
            "status": "error",
            "message": f"Runbook '{runbook_id}' not found. "
                       f"Available: {list(runbooks.keys())}",
        }

    rb = runbooks[runbook_id]
    steps = []
    for step in rb.get("steps", []):
        annotated = dict(step)
        annotated["risk_tier"] = _classify_step_risk(step)
        steps.append(annotated)

    return {
        "runbook_id": runbook_id,
        "name": rb.get("name", runbook_id),
        "description": rb.get("description", ""),
        "steps": steps,
        "step_count": len(steps),
        "high_risk_steps": [s["id"] for s in steps if s["risk_tier"] == "HIGH"],
    }


@with_guardrail
async def execute_runbook_step(
    tool_context: ToolContext,
    runbook_id: str,
    step_id: str,
    dry_run: bool = True,
    params: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Execute a single runbook step.

    Safety rules:
    - dry_run=True (default): always returns simulated output, never executes.
    - dry_run=False + HIGH risk: requires an APPROVED approval record in session state.
    - dry_run=False + LOW/MEDIUM: executes (currently returns dry_run_output; real
      execution is intentionally disabled for safety).
    - Arbitrary shell commands are never accepted; only pre-defined runbook steps run.

    Args:
        runbook_id: Runbook identifier.
        step_id:    Step identifier within the runbook.
        dry_run:    If True, return simulated output only (default: True).
        params:     Optional template substitution params (e.g. {"service_name": "api"}).

    Returns:
        Execution result dict.
    """
    runbooks = _load_runbooks()
    if runbook_id not in runbooks:
        return {"status": "error", "message": f"Runbook '{runbook_id}' not found."}

    rb = runbooks[runbook_id]
    step = next((s for s in rb.get("steps", []) if s["id"] == step_id), None)
    if step is None:
        return {
            "status": "error",
            "message": f"Step '{step_id}' not found in runbook '{runbook_id}'.",
        }

    risk_tier = _classify_step_risk(step)
    dry_run_output = step.get("dry_run_output", f"[dry-run] {step.get('command', '')}")

    # Apply template substitution if params provided
    if params:
        for key, val in params.items():
            dry_run_output = dry_run_output.replace(f"{{{key}}}", str(val))

    # --- Dry-run path: always safe ---
    if dry_run:
        return {
            "status": "success",
            "runbook_id": runbook_id,
            "step_id": step_id,
            "risk_tier": risk_tier,
            "dry_run": True,
            "output": dry_run_output,
            "message": f"[DRY-RUN] {step.get('description', step_id)}: {dry_run_output}",
        }

    # --- Real execution path ---
    if risk_tier == "HIGH":
        # Check for an approved record
        approvals = tool_context.state.get("pending_approvals", {})
        approved = any(
            r["status"] == "APPROVED"
            and r.get("context_data", {}).get("runbook_id") == runbook_id
            and r.get("context_data", {}).get("step_id") == step_id
            for r in approvals.values()
        )
        if not approved:
            # Request approval and block
            from opsmind.tools.approval import request_human_approval
            approval_result = await request_human_approval(
                tool_context=tool_context,
                action=f"{runbook_id}/{step_id}",
                description=step.get("description", step_id),
                risk_tier=risk_tier,
                context_data={"runbook_id": runbook_id, "step_id": step_id},
            )
            return {
                "status": "pending_approval",
                "runbook_id": runbook_id,
                "step_id": step_id,
                "risk_tier": risk_tier,
                "approval_id": approval_result.get("approval_id"),
                "message": approval_result.get("message"),
            }

    # Real execution is intentionally disabled; return dry-run output
    # (prevents arbitrary command execution while keeping the approval flow testable)
    logger.info(
        "Executing step %s/%s (risk=%s, dry_run=False — returning simulated output)",
        runbook_id, step_id, risk_tier,
    )
    return {
        "status": "success",
        "runbook_id": runbook_id,
        "step_id": step_id,
        "risk_tier": risk_tier,
        "dry_run": False,
        "output": dry_run_output,
        "message": f"[EXECUTED] {step.get('description', step_id)}: {dry_run_output}",
    }
