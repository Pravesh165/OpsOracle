"""
Jira write automation tools for OPS-Mind.
Supports live JIRA REST API v2 execution and simulated/test mode when credentials
are absent or simulation is explicitly requested.
Decorated with @audit_action and @with_guardrail for safety.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    from typing import Any as ToolContext  # type: ignore

from opsmind.audit.decorator import audit_action
try:
    from opsmind.config import get_jira_config
except ImportError:
    def get_jira_config():
        return {}
from opsmind.tools.guardrail import with_guardrail

logger = logging.getLogger(__name__)


def _get_jira_connector():
    from opsmind.data.connectors.jira import create_jira_connector
    return create_jira_connector()



def _is_jira_configured() -> bool:
    """Check if valid, non-placeholder Jira credentials exist in environment."""
    cfg = get_jira_config()
    base_url = str(cfg.get("base_url") or "").strip()
    username = str(cfg.get("username") or "").strip()
    api_token = str(cfg.get("api_token") or "").strip()

    if not (base_url and username and api_token):
        return False

    # Check for default template placeholders
    placeholders = ["your-domain.atlassian.net", "user@company.com", "your-api-token", "example.com"]
    for ph in placeholders:
        if ph in base_url or ph in username or ph in api_token:
            return False

    return True


@with_guardrail
@audit_action("jira_create_issue", tool_name="create_jira_ticket")
async def create_jira_ticket(
    tool_context: ToolContext,
    summary: str,
    description: str,
    project_key: Optional[str] = None,
    issue_type: str = "Incident",
    priority: Optional[str] = None,
    labels: Optional[List[str]] = None,
    simulate: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Create a new JIRA issue/ticket for an incident or task.
    Falls back to simulated mode if live credentials are not configured.

    Args:
        tool_context: ADK ToolContext
        summary: Title/summary of the issue
        description: Detailed incident description or remediation plan
        project_key: JIRA project key (defaults to first in JIRA_PROJECT_KEYS or 'OPS')
        issue_type: Issue type name (default 'Incident' or 'Bug')
        priority: Priority name (e.g. 'Highest', 'High', 'Medium', 'Low')
        labels: Optional tags/labels list
        simulate: Explicitly force simulation mode if True

    Returns:
        Dictionary containing issue key, id, URL, and creation status
    """
    cfg = get_jira_config()
    target_project = project_key or (cfg.get("project_keys") or ["OPS"])[0] or "OPS"
    labels_list = labels or ["opsmind", "incident-response"]

    should_simulate = simulate if simulate is not None else (not _is_jira_configured())

    if should_simulate:
        mock_id = f"{int(datetime.now(timezone.utc).timestamp()) % 100000:05d}"
        issue_key = f"{target_project}-{mock_id}"
        base_url = (cfg.get("base_url") or "https://mock-jira.internal").rstrip("/")
        simulated_result = {
            "status": "success",
            "simulated": True,
            "key": issue_key,
            "id": f"sim-{uuid.uuid4().hex[:8]}",
            "summary": summary,
            "project": target_project,
            "issue_type": issue_type,
            "priority": priority or "High",
            "labels": labels_list,
            "url": f"{base_url}/browse/{issue_key}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": f"Simulated JIRA ticket {issue_key} created successfully",
        }
        logger.info(f"[SIMULATED] Created JIRA ticket {issue_key}: {summary}")
        return simulated_result

    # Real mode
    try:
        connector = _get_jira_connector()
        connected = await connector.connect()
        if not connected:
            raise ConnectionError("Failed to connect to configured JIRA instance")

        try:
            res = await connector.create_issue(
                project_key=target_project,
                summary=summary,
                description=description,
                issue_type=issue_type,
                priority=priority,
                labels=labels_list,
            )
            created_key = res.get("key", f"{target_project}-NEW")
            base_url = (cfg.get("base_url") or "").rstrip("/")
            return {
                "status": "success",
                "simulated": False,
                "key": created_key,
                "id": str(res.get("id")),
                "url": f"{base_url}/browse/{created_key}",
                "message": f"JIRA ticket {created_key} created successfully",
            }
        finally:
            await connector.disconnect()

    except Exception as exc:
        logger.error(f"Error creating real JIRA ticket: {exc}")
        return {
            "status": "error",
            "simulated": False,
            "message": f"Failed to create JIRA ticket: {exc}",
        }


@with_guardrail
@audit_action("jira_add_comment", tool_name="add_jira_comment")
async def add_jira_comment(
    tool_context: ToolContext,
    issue_key: str,
    comment_body: str,
    simulate: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Add a comment to an existing JIRA ticket.

    Args:
        tool_context: ADK ToolContext
        issue_key: Key of the JIRA issue (e.g. 'OPS-101')
        comment_body: Markdown or text content for the comment
        simulate: Explicitly force simulation mode if True

    Returns:
        Dictionary containing comment ID and status
    """
    cfg = get_jira_config()
    should_simulate = simulate if simulate is not None else (not _is_jira_configured())

    if should_simulate:
        comment_id = f"comment-sim-{uuid.uuid4().hex[:6]}"
        simulated_result = {
            "status": "success",
            "simulated": True,
            "issue_key": issue_key,
            "comment_id": comment_id,
            "body_snippet": comment_body[:100] + ("..." if len(comment_body) > 100 else ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": f"Simulated comment added to {issue_key}",
        }
        logger.info(f"[SIMULATED] Added comment to JIRA ticket {issue_key}")
        return simulated_result

    try:
        connector = _get_jira_connector()
        connected = await connector.connect()
        if not connected:
            raise ConnectionError("Failed to connect to configured JIRA instance")

        try:
            res = await connector.add_comment(issue_key=issue_key, body=comment_body)
            return {
                "status": "success",
                "simulated": False,
                "issue_key": issue_key,
                "comment_id": str(res.get("id")),
                "message": f"Comment added to JIRA ticket {issue_key}",
            }
        finally:
            await connector.disconnect()

    except Exception as exc:
        logger.error(f"Error adding comment to JIRA issue {issue_key}: {exc}")
        return {
            "status": "error",
            "simulated": False,
            "issue_key": issue_key,
            "message": f"Failed to add comment: {exc}",
        }


@with_guardrail
@audit_action("jira_transition_issue", tool_name="transition_jira_issue")
async def transition_jira_issue(
    tool_context: ToolContext,
    issue_key: str,
    target_status: str,
    simulate: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Transition a JIRA ticket to a new status (e.g. 'In Progress', 'Resolved', 'Closed').

    Args:
        tool_context: ADK ToolContext
        issue_key: Key of the JIRA issue (e.g. 'OPS-101')
        target_status: Name of transition or target status
        simulate: Explicitly force simulation mode if True

    Returns:
        Dictionary containing transition result
    """
    should_simulate = simulate if simulate is not None else (not _is_jira_configured())

    if should_simulate:
        simulated_result = {
            "status": "success",
            "simulated": True,
            "issue_key": issue_key,
            "target_status": target_status,
            "transitioned_at": datetime.now(timezone.utc).isoformat(),
            "message": f"Simulated transition of {issue_key} to '{target_status}' succeeded",
        }
        logger.info(f"[SIMULATED] Transitioned JIRA ticket {issue_key} to {target_status}")
        return simulated_result

    try:
        connector = _get_jira_connector()
        connected = await connector.connect()
        if not connected:
            raise ConnectionError("Failed to connect to configured JIRA instance")

        try:
            res = await connector.transition_issue(
                issue_key=issue_key,
                transition_name_or_id=target_status
            )
            return {
                "status": "success",
                "simulated": False,
                "issue_key": issue_key,
                "transition_id": res.get("transition_id"),
                "message": f"Issue {issue_key} transitioned to {target_status}",
            }
        finally:
            await connector.disconnect()

    except Exception as exc:
        logger.error(f"Error transitioning JIRA issue {issue_key}: {exc}")
        return {
            "status": "error",
            "simulated": False,
            "issue_key": issue_key,
            "message": f"Failed to transition issue: {exc}",
        }
