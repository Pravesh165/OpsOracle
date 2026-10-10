"""
Incident triage tools for OpsMind.

Provides severity scoring, team routing, and a state machine for incident lifecycle.
All state is stored in tool_context.state so it persists across agent turns.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.adk.tools.tool_context import ToolContext

from opsmind.config import logger
from opsmind.tools.guardrail import with_guardrail
from opsmind.audit.decorator import audit_action
from opsmind.tools.jira_write import create_jira_ticket

# ---------------------------------------------------------------------------
# Severity matrix  (priority, category) → base score 0–1
# ---------------------------------------------------------------------------
_SEVERITY_MATRIX: Dict[tuple, float] = {
    ("P1", "network"):    1.0,
    ("P1", "database"):   0.95,
    ("P1", "security"):   1.0,
    ("P1", "software"):   0.85,
    ("P1", "hardware"):   0.80,
    ("P1", "inquiry"):    0.60,
    ("P2", "network"):    0.70,
    ("P2", "database"):   0.65,
    ("P2", "security"):   0.80,
    ("P2", "software"):   0.55,
    ("P2", "hardware"):   0.50,
    ("P2", "inquiry"):    0.35,
    ("P3", "network"):    0.45,
    ("P3", "database"):   0.40,
    ("P3", "security"):   0.55,
    ("P3", "software"):   0.30,
    ("P3", "hardware"):   0.25,
    ("P3", "inquiry"):    0.15,
    ("P4", "network"):    0.20,
    ("P4", "database"):   0.18,
    ("P4", "security"):   0.30,
    ("P4", "software"):   0.12,
    ("P4", "hardware"):   0.10,
    ("P4", "inquiry"):    0.05,
}

# Keyword boosters applied to the symptom / description text
_KEYWORD_BOOSTERS: Dict[str, float] = {
    "outage":       0.20,
    "down":         0.15,
    "data loss":    0.30,
    "breach":       0.30,
    "customer":     0.15,
    "production":   0.10,
    "critical":     0.15,
    "unavailable":  0.15,
    "degraded":     0.10,
    "escalat":      0.10,   # matches "escalated", "escalation"
}

# Team routing by category (fallback: "ops-team")
_ROUTING_MAP: Dict[str, str] = {
    "network":   "network-ops",
    "database":  "database-ops",
    "security":  "security-ops",
    "software":  "software-ops",
    "hardware":  "hardware-ops",
    "inquiry":   "service-desk",
}

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------
_VALID_TRANSITIONS: Dict[str, List[str]] = {
    "DETECTED":    ["TRIAGED"],
    "TRIAGED":     ["ACKNOWLEDGED", "ESCALATED"],
    "ACKNOWLEDGED":["MITIGATING", "ESCALATED"],
    "MITIGATING":  ["RESOLVED", "ESCALATED"],
    "ESCALATED":   ["MITIGATING", "RESOLVED"],
    "RESOLVED":    ["CLOSED"],
    "CLOSED":      [],
}


# ---------------------------------------------------------------------------
# Public helpers (pure functions — no ToolContext needed, easy to unit-test)
# ---------------------------------------------------------------------------

def _severity_score(
    priority: str,
    category: str,
    keywords: str = "",
) -> float:
    """
    Compute severity score 0–1 from priority, category, and free-text keywords.

    Priority values accepted: P1/1/Critical, P2/2/High, P3/3/Medium, P4/4/Low.
    Category is matched case-insensitively.
    """
    p = _normalise_priority(priority)
    c = category.lower().strip() if category else "software"

    base = _SEVERITY_MATRIX.get((p, c))
    if base is None:
        # Unknown category: use priority-only fallback
        priority_defaults = {"P1": 0.75, "P2": 0.50, "P3": 0.25, "P4": 0.10}
        base = priority_defaults.get(p, 0.10)

    boost = 0.0
    kw_lower = keywords.lower()
    for kw, delta in _KEYWORD_BOOSTERS.items():
        if kw in kw_lower:
            boost += delta

    return min(1.0, round(base + boost, 4))


def _normalise_priority(raw: str) -> str:
    """Map various priority representations to P1–P4."""
    mapping = {
        "1": "P1", "p1": "P1", "critical": "P1",
        "2": "P2", "p2": "P2", "high": "P2",
        "3": "P3", "p3": "P3", "medium": "P3", "moderate": "P3",
        "4": "P4", "p4": "P4", "low": "P4",
    }
    return mapping.get(str(raw).lower().strip(), "P3")


def _route_team(category: str) -> str:
    return _ROUTING_MAP.get(category.lower().strip(), "ops-team")


def _urgency_label(score: float) -> str:
    if score >= 0.9:
        return "CRITICAL"
    if score >= 0.7:
        return "HIGH"
    if score >= 0.4:
        return "MEDIUM"
    return "LOW"


def _impact_label(score: float) -> str:
    if score >= 0.9:
        return "enterprise-wide"
    if score >= 0.7:
        return "multi-team"
    if score >= 0.4:
        return "single-team"
    return "individual"


# ---------------------------------------------------------------------------
# ADK tool functions
# ---------------------------------------------------------------------------

@with_guardrail
@audit_action("triage_incident", tool_name="triage_incident")
async def triage_incident(
    tool_context: ToolContext,
    incident_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Triage an incident: compute severity, urgency, impact, affected service,
    and suggested owner team. Automatically creates a JIRA ticket for P1 incidents.

    Args:
        incident_data: Dict with keys: priority, category, symptom (or description),
                       number (optional), affected_service (optional).

    Returns:
        Triage result dict stored in session state under
        tool_context.state["incident_states"][incident_id].
    """
    try:
        priority = str(incident_data.get("priority", "P3"))
        category = str(incident_data.get("category", "software"))
        symptom = str(
            incident_data.get("symptom")
            or incident_data.get("u_symptom")
            or incident_data.get("description")
            or ""
        )
        incident_id = str(
            incident_data.get("number")
            or incident_data.get("id")
            or incident_data.get("incident_id")
            or f"INC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        affected_service = str(
            incident_data.get("affected_service")
            or incident_data.get("cmdb_ci")
            or incident_data.get("business_service")
            or category
        )

        score = _severity_score(priority, category, symptom)
        team = _route_team(category)
        urgency = _urgency_label(score)
        impact = _impact_label(score)
        norm_priority = _normalise_priority(priority)

        result: Dict[str, Any] = {
            "incident_id": incident_id,
            "severity": score,
            "urgency": urgency,
            "impact": impact,
            "affected_service": affected_service,
            "suggested_team": team,
            "priority_normalised": norm_priority,
            "category": category,
            "state": "TRIAGED",
            "triaged_at": datetime.now().isoformat(),
            "routing_reason": (
                f"Category '{category}' maps to {team}; "
                f"severity {score:.2f} ({urgency})"
            ),
        }

        # For P1 incidents, automatically create or link a JIRA ticket
        if norm_priority == "P1" or score >= 0.9:
            jira_summary = f"[P1 Incident] {incident_id}: {affected_service} - {symptom[:80] if symptom else 'High Priority Outage'}"
            jira_desc = (
                f"h2. Automated Incident Escalation\n\n"
                f"*Incident ID:* {incident_id}\n"
                f"*Severity:* {score:.2f} ({urgency})\n"
                f"*Category:* {category}\n"
                f"*Affected Service:* {affected_service}\n"
                f"*Routed Team:* {team}\n\n"
                f"h3. Symptom\n{symptom or 'No detailed symptom provided.'}\n"
            )
            try:
                jira_ticket = await create_jira_ticket(
                    tool_context=tool_context,
                    summary=jira_summary,
                    description=jira_desc,
                    issue_type="Incident",
                    priority="Highest",
                    labels=["p1-escalation", "opsmind", category.lower()],
                )
                result["jira_ticket"] = jira_ticket
                logger.info(
                    "Auto-created JIRA ticket for P1 incident %s: %s",
                    incident_id,
                    jira_ticket.get("key"),
                )
            except Exception as jira_err:
                logger.warning("Failed to auto-create JIRA ticket for P1 incident %s: %s", incident_id, jira_err)
                result["jira_ticket_error"] = str(jira_err)

        # Persist in session state
        states: Dict[str, Any] = tool_context.state.get("incident_states", {})
        states[incident_id] = result
        tool_context.state["incident_states"] = states

        # Also mark initial state transition
        _store_state(tool_context, incident_id, "TRIAGED")

        logger.info(
            "Triaged %s: severity=%.2f urgency=%s team=%s",
            incident_id, score, urgency, team,
        )
        return result

    except Exception as exc:
        logger.error("Error triaging incident: %s", exc)
        return {"status": "error", "message": str(exc)}



@with_guardrail
async def get_triage_status(
    tool_context: ToolContext,
    incident_id: str,
) -> Dict[str, Any]:
    """
    Return the current triage state for an incident.

    Args:
        incident_id: The incident identifier.

    Returns:
        Triage result dict, or a not-found message.
    """
    states: Dict[str, Any] = tool_context.state.get("incident_states", {})
    if incident_id in states:
        return {"found": True, "triage": states[incident_id]}
    return {
        "found": False,
        "incident_id": incident_id,
        "message": f"No triage record found for {incident_id}",
    }


@with_guardrail
async def transition_incident_state(
    tool_context: ToolContext,
    incident_id: str,
    new_state: str,
) -> Dict[str, Any]:
    """
    Transition an incident to a new state.

    Valid states: DETECTED → TRIAGED → ACKNOWLEDGED → MITIGATING → RESOLVED → CLOSED
                                     ↘ ESCALATED ↗

    Args:
        incident_id: The incident identifier.
        new_state: Target state (case-insensitive).

    Returns:
        Updated state record, or raises ValueError on invalid transition.
    """
    new_state = new_state.upper().strip()
    states: Dict[str, Any] = tool_context.state.get("incident_states", {})

    # Auto-create a minimal record if not yet triaged
    if incident_id not in states:
        states[incident_id] = {
            "incident_id": incident_id,
            "state": "DETECTED",
            "state_history": [],
        }

    record = states[incident_id]
    current = record.get("state", "DETECTED")

    allowed = _VALID_TRANSITIONS.get(current, [])
    if new_state not in allowed:
        raise ValueError(
            f"Invalid transition: {current} → {new_state}. "
            f"Allowed from {current}: {allowed}"
        )

    history: List[Dict[str, str]] = record.get("state_history", [])
    history.append({
        "from": current,
        "to": new_state,
        "at": datetime.now().isoformat(),
    })
    record["state"] = new_state
    record["state_history"] = history
    states[incident_id] = record
    tool_context.state["incident_states"] = states

    logger.info("Incident %s: %s → %s", incident_id, current, new_state)
    return {
        "incident_id": incident_id,
        "previous_state": current,
        "new_state": new_state,
        "transitioned_at": datetime.now().isoformat(),
    }


@with_guardrail
async def close_incident(
    tool_context: ToolContext,
    incident_id: str,
) -> Dict[str, Any]:
    """
    Close a RESOLVED incident (RESOLVED → CLOSED).

    Args:
        incident_id: The incident identifier.

    Returns:
        Updated state record.
    """
    return await transition_incident_state(tool_context, incident_id, "CLOSED")


@with_guardrail
async def reopen_incident(
    tool_context: ToolContext,
    incident_id: str,
    reason: str = "",
) -> Dict[str, Any]:
    """
    Re-open a closed or resolved incident back to MITIGATING for re-investigation.

    Bypasses the normal state machine to allow re-opening from any terminal state.

    Args:
        incident_id: The incident identifier.
        reason: Optional reason for re-opening.

    Returns:
        Updated state record.
    """
    states: Dict[str, Any] = tool_context.state.get("incident_states", {})
    if incident_id not in states:
        states[incident_id] = {
            "incident_id": incident_id,
            "state": "DETECTED",
            "state_history": [],
        }

    record = states[incident_id]
    current = record.get("state", "DETECTED")

    history: List[Dict[str, str]] = record.get("state_history", [])
    history.append({
        "from": current,
        "to": "MITIGATING",
        "at": datetime.now().isoformat(),
        "reason": reason or "re-opened for re-investigation",
    })
    record["state"] = "MITIGATING"
    record["state_history"] = history
    record["reopened_at"] = datetime.now().isoformat()
    record["reopen_reason"] = reason
    states[incident_id] = record
    tool_context.state["incident_states"] = states

    logger.info("Incident %s re-opened: %s → MITIGATING (reason: %s)", incident_id, current, reason)
    return {
        "incident_id": incident_id,
        "previous_state": current,
        "new_state": "MITIGATING",
        "transitioned_at": datetime.now().isoformat(),
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Internal helper (no ToolContext — used by transition_incident_state too)
# ---------------------------------------------------------------------------

def _store_state(tool_context: ToolContext, incident_id: str, state: str) -> None:
    """Initialise state history for a freshly triaged incident."""
    states: Dict[str, Any] = tool_context.state.get("incident_states", {})
    record = states.get(incident_id, {})
    if "state_history" not in record:
        record["state_history"] = [
            {"from": "DETECTED", "to": state, "at": datetime.now().isoformat()}
        ]
    states[incident_id] = record
    tool_context.state["incident_states"] = states
