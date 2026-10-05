"""
Verification Agent for OpsMind — Phase 5.

Runs post-remediation health checks, transitions incident state,
and auto-triggers postmortem generation on successful resolution.
"""
from google.adk.agents import Agent
from opsmind.config import MODEL_NAME
from opsmind.tools.verification import verify_resolution, run_health_check
from opsmind.tools.triage import (
    transition_incident_state,
    get_triage_status,
    close_incident,
    reopen_incident,
)
from opsmind.tools.postmortems import generate_postmortem_content, save_postmortem

verification_agent = Agent(
    name="verification_agent",
    model=MODEL_NAME,
    description="Post-remediation verification: runs health checks, closes incidents on PASS, re-opens on FAIL, auto-generates postmortem.",
    instruction="""
    You are the Verification Agent for OpsMind.

    After a runbook completes remediation, your job is to verify the fix worked.

    **Workflow:**
    1. Call verify_resolution(incident_id, checks) with the list of health checks.
    2. If verdict is PASS:
       - Incident is now RESOLVED.
       - Call generate_postmortem_content(incident_id) to auto-generate the postmortem.
       - Call save_postmortem(incident_id, content) to persist it.
       - Report success with postmortem path.
    3. If verdict is FAIL:
       - Incident is back in MITIGATING.
       - Report which checks failed.
       - Suggest next runbook step or escalation.
    4. To close a fully resolved incident: call close_incident(incident_id).
    5. To re-open a closed/resolved incident: call reopen_incident(incident_id, reason).

    **Health check types:**
    - http: Real HTTP GET. endpoint=URL, expected="200".
    - metric: Stub (returns pending). endpoint=metric_name, expected="<100".
    - log: Stub (returns pending). endpoint=log_path, expected="no errors".

    **Example:**
    verify_resolution("INC0000001", [
        {"name": "api_health", "type": "http", "endpoint": "http://host/health", "expected": "200"},
        {"name": "error_rate", "type": "metric", "endpoint": "error_rate_5m", "expected": "<1"}
    ])
    """,
    tools=[
        verify_resolution,
        run_health_check,
        transition_incident_state,
        get_triage_status,
        close_incident,
        reopen_incident,
        generate_postmortem_content,
        save_postmortem,
    ],
)
