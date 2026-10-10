"""
Audit listing tool for OPS-Mind agents.
Allows agents to query and present structured audit events.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    from typing import Any as ToolContext  # type: ignore

from opsmind.audit.logger import AuditLogger
from opsmind.tools.guardrail import with_guardrail

logger = logging.getLogger(__name__)


@with_guardrail
async def list_audit_events(
    tool_context: ToolContext,
    action: Optional[str] = None,
    tool: Optional[str] = None,
    session_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    List structured audit events from the audit log.

    Args:
        tool_context: ADK tool context
        action: Filter by action type (e.g. 'jira_create_issue', 'triage_incident')
        tool: Filter by tool name
        session_id: Filter by session identifier
        start_time: ISO UTC start timestamp
        end_time: ISO UTC end timestamp
        limit: Max events to return (default 50)

    Returns:
        Dictionary containing total count and list of audit events
    """
    try:
        audit_logger = AuditLogger.get_instance()
        events = audit_logger.query_events(
            action=action,
            tool=tool,
            session_id=session_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        return {
            "status": "success",
            "count": len(events),
            "events": events,
        }
    except Exception as exc:
        logger.error(f"Error querying audit events: {exc}")
        return {
            "status": "error",
            "message": str(exc),
            "events": [],
        }
