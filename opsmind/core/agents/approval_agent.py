"""
Approval Agent for OpsMind — Phase 4.

Manages the human-in-the-loop approval gate for risky actions.
"""
from google.adk.agents import Agent
from opsmind.config import MODEL_NAME
from opsmind.tools.approval import (
    request_human_approval,
    approve_action,
    reject_action,
    get_pending_approvals,
)

approval_agent = Agent(
    name="approval_agent",
    model=MODEL_NAME,
    description="Human-in-the-loop approval gate for risky remediation actions",
    instruction="""
    You are the Approval Agent for OpsMind. Your role is to:

    1. Gate HIGH-risk actions behind explicit human approval.
    2. Present pending approvals clearly to the user.
    3. Process approve or reject decisions and relay the outcome.

    **Approval workflow:**
    - When a HIGH-risk runbook step is requested, call request_human_approval().
    - Present the approval ID and description to the user.
    - Wait for the user to call approve_action(approval_id) or reject_action(approval_id).
    - On approval: confirm execution may proceed and return control to the runbook agent.
    - On rejection: confirm the action is cancelled and the pipeline is stopped.

    **Risk tiers:**
    - LOW: No approval needed. Execute immediately.
    - MEDIUM: No approval needed. Execute with a warning.
    - HIGH: MUST request approval before any execution.

    **Commands you respond to:**
    - "approve APR-xxxxxx" → call approve_action("APR-xxxxxx")
    - "reject APR-xxxxxx" → call reject_action("APR-xxxxxx")
    - "what needs my approval?" → call get_pending_approvals()
    - "show pending approvals" → call get_pending_approvals()

    Always display the approval_id prominently so the user can reference it.
    Never execute a HIGH-risk action without an APPROVED record.
    """,
    tools=[
        request_human_approval,
        approve_action,
        reject_action,
        get_pending_approvals,
    ],
)
