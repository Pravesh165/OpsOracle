"""
Human-in-the-loop approval gate for OpsMind — Phase 4.

All approval state lives in tool_context.state["pending_approvals"] so it
persists across agent turns within a session.

Approval IDs are formatted APR-<6-digit-zero-padded-counter>.
"""
from datetime import datetime
from typing import Any, Dict, List

from google.adk.tools.tool_context import ToolContext

from opsmind.config import logger
from opsmind.tools.guardrail import with_guardrail

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _next_approval_id(tool_context: ToolContext) -> str:
    counter = tool_context.state.get("_approval_counter", 0) + 1
    tool_context.state["_approval_counter"] = counter
    return f"APR-{counter:06d}"


def _get_approvals(tool_context: ToolContext) -> Dict[str, Any]:
    return tool_context.state.get("pending_approvals", {})


def _set_approvals(tool_context: ToolContext, approvals: Dict[str, Any]) -> None:
    tool_context.state["pending_approvals"] = approvals


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

@with_guardrail
async def request_human_approval(
    tool_context: ToolContext,
    action: str,
    description: str,
    risk_tier: str,
    context_data: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Create a pending approval record and pause execution until resolved.

    Args:
        action:       Short action name (e.g. "graceful_restart").
        description:  Human-readable description of what will happen.
        risk_tier:    "LOW" | "MEDIUM" | "HIGH".
        context_data: Optional extra metadata (runbook_id, step_id, …).

    Returns:
        Dict with approval_id and status=PENDING.
    """
    approval_id = _next_approval_id(tool_context)
    record: Dict[str, Any] = {
        "approval_id": approval_id,
        "action": action,
        "description": description,
        "risk_tier": risk_tier.upper(),
        "status": "PENDING",
        "requested_at": datetime.now().isoformat(),
        "resolved_at": None,
        "context_data": context_data or {},
    }

    approvals = _get_approvals(tool_context)
    approvals[approval_id] = record
    _set_approvals(tool_context, approvals)

    logger.info("Approval requested: %s (%s) risk=%s", approval_id, action, risk_tier)
    return {
        "approval_id": approval_id,
        "status": "PENDING",
        "message": (
            f"⚠️ Action '{action}' requires human approval (risk: {risk_tier.upper()}). "
            f"Approval ID: {approval_id}. "
            f"Call approve_action('{approval_id}') to proceed or "
            f"reject_action('{approval_id}') to cancel."
        ),
        "risk_tier": risk_tier.upper(),
        "description": description,
    }


@with_guardrail
async def approve_action(
    tool_context: ToolContext,
    approval_id: str,
) -> Dict[str, Any]:
    """
    Approve a pending action.

    Args:
        approval_id: The APR-xxxxxx identifier returned by request_human_approval.

    Returns:
        Updated approval record with status=APPROVED.
    """
    approvals = _get_approvals(tool_context)
    if approval_id not in approvals:
        return {
            "status": "error",
            "message": f"Approval ID '{approval_id}' not found.",
        }

    record = approvals[approval_id]
    if record["status"] != "PENDING":
        return {
            "status": "error",
            "message": f"Approval '{approval_id}' is already {record['status']}.",
        }

    record["status"] = "APPROVED"
    record["resolved_at"] = datetime.now().isoformat()
    approvals[approval_id] = record
    _set_approvals(tool_context, approvals)

    logger.info("Approval granted: %s (%s)", approval_id, record["action"])
    return {
        "approval_id": approval_id,
        "status": "APPROVED",
        "action": record["action"],
        "message": f"✅ Action '{record['action']}' approved. Execution may proceed.",
    }


@with_guardrail
async def reject_action(
    tool_context: ToolContext,
    approval_id: str,
    reason: str = "",
) -> Dict[str, Any]:
    """
    Reject a pending action, blocking execution.

    Args:
        approval_id: The APR-xxxxxx identifier.
        reason:      Optional rejection reason.

    Returns:
        Dict with status=REJECTED.
    """
    approvals = _get_approvals(tool_context)
    if approval_id not in approvals:
        return {
            "status": "error",
            "message": f"Approval ID '{approval_id}' not found.",
        }

    record = approvals[approval_id]
    if record["status"] != "PENDING":
        return {
            "status": "error",
            "message": f"Approval '{approval_id}' is already {record['status']}.",
        }

    record["status"] = "REJECTED"
    record["resolved_at"] = datetime.now().isoformat()
    record["rejection_reason"] = reason
    approvals[approval_id] = record
    _set_approvals(tool_context, approvals)

    logger.info("Approval rejected: %s (%s) reason=%s", approval_id, record["action"], reason)
    return {
        "approval_id": approval_id,
        "status": "rejected",
        "action": record["action"],
        "reason": reason,
        "message": f"❌ Action '{record['action']}' rejected. Pipeline stopped.",
    }


@with_guardrail
async def get_pending_approvals(
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """
    List all pending approval requests in the current session.

    Returns:
        Dict with list of pending approval records.
    """
    approvals = _get_approvals(tool_context)
    pending = [r for r in approvals.values() if r["status"] == "PENDING"]
    all_records = list(approvals.values())

    return {
        "pending_count": len(pending),
        "total_count": len(all_records),
        "pending": pending,
        "all": all_records,
        "message": (
            f"{len(pending)} pending approval(s) awaiting your decision."
            if pending else "No pending approvals."
        ),
    }
