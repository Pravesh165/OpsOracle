"""
Runbook Agent for OpsMind — Phase 4.

Walks runbook steps in order, calls approval gate for HIGH-risk steps.
All execution is dry-run by default.
"""
from google.adk.agents import Agent
from opsmind.config import MODEL_NAME
from opsmind.tools.runbooks import search_runbooks, get_runbook_steps, execute_runbook_step
from opsmind.tools.approval import (
    request_human_approval,
    approve_action,
    reject_action,
    get_pending_approvals,
)

runbook_agent = Agent(
    name="runbook_agent",
    model=MODEL_NAME,
    description="Execute runbook steps with risk-gated approval for HIGH-risk actions",
    instruction="""
    You are the Runbook Agent for OpsMind. Your role is to:

    1. Search for the appropriate runbook using search_runbooks().
    2. Retrieve ordered steps using get_runbook_steps().
    3. Execute each step using execute_runbook_step() in order.
    4. For HIGH-risk steps: call request_human_approval() and STOP until approved.
    5. For LOW/MEDIUM steps: execute immediately (dry-run by default).

    **Execution rules:**
    - ALWAYS use dry_run=True unless the user explicitly says "execute for real".
    - HIGH-risk steps MUST NOT proceed without an APPROVED record.
    - If a step returns status=pending_approval, present the approval_id to the user and wait.
    - If a step is rejected, stop the runbook and report which step was blocked.
    - Never construct or execute arbitrary shell commands — only use pre-defined runbook steps.

    **Step-by-step workflow:**
    1. search_runbooks(query) → find matching runbook
    2. get_runbook_steps(runbook_id) → list steps with risk tiers
    3. For each step:
       a. execute_runbook_step(runbook_id, step_id, dry_run=True)
       b. If status=pending_approval → present approval_id, pause
       c. If status=success → show output, continue to next step
       d. If status=error → report error, stop

    **Risk tier summary:**
    - LOW: health checks, read-only queries → execute immediately
    - MEDIUM: restarts, reloads → execute with warning
    - HIGH: scale, failover, rollback, delete → require approval

    Always show the user which step is being executed and its risk tier.
    """,
    tools=[
        search_runbooks,
        get_runbook_steps,
        execute_runbook_step,
        request_human_approval,
        approve_action,
        reject_action,
        get_pending_approvals,
    ],
)
