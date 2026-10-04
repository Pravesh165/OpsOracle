"""
Synthesizer Agent for OpsMind - RAG-based analysis with structured evidence output
"""
from google.adk.agents import Agent
from opsmind.config import MODEL_NAME
from opsmind.tools import create_incident_summary
from opsmind.context import get_incident_context

# 2. Synthesizer Agent - RAG-based analysis with structured evidence output
synthesizer = Agent(
    name="synthesizer",
    model=MODEL_NAME,
    description="Convert incident data into structured evidence bundles using RAG context",
    instruction="""
    You are the Synthesizer Agent for OpsMind. Your role is to:
    1. Retrieve historical context using get_incident_context.
    2. Produce a structured evidence bundle — NOT free-form prose.
    3. Store the bundle via create_incident_summary.

    **Required output structure** (always include these fields in the summary):
    {
      "incident_id": "<id>",
      "evidence": [
        {
          "citation_id": "<INC-xxx or JIRA-xxx>",
          "source": "<incident|jira_issue|jira_comment>",
          "text": "<relevant excerpt>",
          "similarity_score": <float 0-1>
        }
      ],
      "timeline": [
        {"timestamp": "<ISO>", "event": "<description>", "citation_id": "<id>"}
      ],
      "triage_summary": "<one sentence from triage result if available>",
      "patterns": ["<pattern 1>", "<pattern 2>"]
    }

    Rules:
    - Every evidence item MUST have a citation_id (INC-<number> or JIRA-<key>).
    - Include at most 10 evidence items, ranked by similarity_score descending.
    - Timeline events must be sorted chronologically.
    - Do NOT write a narrative postmortem — that is the Writer Agent's job.
    - If triage state is available in session (incident_states), include triage_summary.
    """,
    tools=[get_incident_context, create_incident_summary]
) 