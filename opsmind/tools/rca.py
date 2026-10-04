"""
Root Cause Analysis tools for OpsMind — Phase 3.

generate_rca()          — LLM-grounded RCA with 5-Whys reasoning; rules fallback
format_citations()      — render [INC-0045][JIRA-WW-712] inline strings
extract_action_items()  — derive action items from RCA + similar resolutions
extract_lessons_learned() — derive lessons from RCA + incident data
"""
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from opsmind.config import logger

# ---------------------------------------------------------------------------
# Citation formatting
# ---------------------------------------------------------------------------

def format_citations(evidence_list: List[Dict[str, Any]]) -> str:
    """
    Render a compact citation string from a list of evidence dicts.

    Each dict must have a 'citation_id' key (e.g. "INC-0045", "JIRA-WW-712").
    Returns a string like "[INC-0045][JIRA-WW-712]".
    Empty / duplicate ids are skipped.
    """
    seen = set()
    parts = []
    for item in evidence_list:
        cid = str(item.get("citation_id", "")).strip()
        if cid and cid not in seen:
            seen.add(cid)
            parts.append(f"[{cid}]")
    return "".join(parts)


def _inline_citations(text: str, evidence_list: List[Dict[str, Any]]) -> str:
    """
    Append a citation block to a text string.
    e.g. "Connection pool exhausted [INC-0045][JIRA-WW-712]"
    """
    cites = format_citations(evidence_list)
    if cites:
        return f"{text} {cites}"
    return text


# ---------------------------------------------------------------------------
# Action items + lessons learned (pure-Python, no LLM required)
# ---------------------------------------------------------------------------

_ACTION_KEYWORDS = {
    "timeout":      "Tune connection/request timeout thresholds and add circuit-breaker logic.",
    "memory":       "Profile memory usage; add heap-size alerts and OOM kill guards.",
    "cpu":          "Identify hot code paths; add CPU throttling and auto-scaling policies.",
    "disk":         "Implement log rotation and disk-usage alerts; archive old data.",
    "network":      "Review network ACLs and firewall rules; add redundant paths.",
    "database":     "Audit slow queries; add read replicas and connection-pool limits.",
    "deploy":       "Enforce canary / blue-green deployments with automated rollback.",
    "config":       "Store configuration in version control; add config-drift detection.",
    "auth":         "Rotate credentials; enforce least-privilege and MFA.",
    "certificate":  "Automate certificate renewal; add expiry monitoring.",
    "dns":          "Add DNS health checks; configure TTL for fast failover.",
    "kubernetes":   "Review pod resource requests/limits; add liveness and readiness probes.",
    "docker":       "Pin image versions; scan images for vulnerabilities in CI.",
    "redis":        "Configure maxmemory-policy; add eviction and replication monitoring.",
    "nginx":        "Review upstream keepalive settings; add upstream health checks.",
}

_LESSON_KEYWORDS = {
    "timeout":      "Timeouts must be tuned per-service; a single global value causes cascading failures.",
    "memory":       "Memory leaks are often masked by restarts; continuous profiling is essential.",
    "cpu":          "CPU spikes under load indicate missing rate-limiting or inefficient algorithms.",
    "disk":         "Disk exhaustion is preventable with proactive capacity planning and alerting.",
    "network":      "Network partitions require explicit retry and fallback strategies in every service.",
    "database":     "Database bottlenecks propagate upstream; isolate read and write workloads early.",
    "deploy":       "Deployments without rollback plans turn minor bugs into major outages.",
    "config":       "Configuration drift between environments is a leading cause of production-only failures.",
    "auth":         "Expired or misconfigured credentials cause silent failures that are hard to diagnose.",
    "certificate":  "Certificate expiry is 100% predictable; automate renewal before it becomes an incident.",
    "dns":          "DNS changes propagate slowly; plan for TTL delays during failover.",
    "kubernetes":   "Pod evictions under resource pressure require pre-defined PodDisruptionBudgets.",
    "docker":       "Unpinned image tags introduce silent regressions across deployments.",
    "redis":        "Redis without a maxmemory policy will consume all available RAM under load.",
    "nginx":        "Upstream timeout mismatches between nginx and backends cause misleading 502/504 errors.",
}


def _keywords_from_text(*texts: str) -> List[str]:
    combined = " ".join(str(t) for t in texts).lower()
    return [kw for kw in _ACTION_KEYWORDS if kw in combined]


def extract_action_items(
    rca_result: Dict[str, Any],
    similar_resolutions: Optional[List[str]] = None,
) -> List[str]:
    """
    Derive concrete action items from RCA output and similar past resolutions.

    Returns a non-empty list even when LLM output is absent.
    """
    items: List[str] = []

    # 1. LLM-authored actions (if present)
    for action in rca_result.get("recommended_actions", []):
        if isinstance(action, str) and action.strip():
            items.append(action.strip())

    # 2. Contributing-factor actions
    for factor in rca_result.get("contributing_factors", []):
        if isinstance(factor, dict):
            action = factor.get("action") or factor.get("recommended_action", "")
            if action and action.strip():
                items.append(action.strip())

    # 3. Keyword-derived actions from root cause text
    root_cause = str(rca_result.get("root_cause", ""))
    for kw in _keywords_from_text(root_cause, *(similar_resolutions or [])):
        candidate = _ACTION_KEYWORDS[kw]
        if candidate not in items:
            items.append(candidate)

    # 4. Always include a postmortem / runbook action
    if not any("runbook" in i.lower() or "postmortem" in i.lower() for i in items):
        items.append("Update runbooks and incident response playbooks based on this postmortem.")

    return items[:8]  # cap at 8


def extract_lessons_learned(
    rca_result: Dict[str, Any],
    incident_data: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Derive lessons learned from RCA output and incident metadata.

    Returns a non-empty list even when LLM output is absent.
    """
    lessons: List[str] = []

    # 1. LLM-authored lessons
    for lesson in rca_result.get("lessons_learned", []):
        if isinstance(lesson, str) and lesson.strip():
            lessons.append(lesson.strip())

    # 2. Keyword-derived lessons from root cause + incident description
    incident_text = ""
    if incident_data:
        incident_text = " ".join(str(v) for v in incident_data.values())
    root_cause = str(rca_result.get("root_cause", ""))
    for kw in _keywords_from_text(root_cause, incident_text):
        candidate = _LESSON_KEYWORDS[kw]
        if candidate not in lessons:
            lessons.append(candidate)

    # 3. Generic fallback
    if not lessons:
        lessons.append(
            "Invest in observability: structured logs, distributed tracing, and SLO-based alerting "
            "reduce mean time to detect and resolve incidents."
        )

    return lessons[:6]  # cap at 6


# ---------------------------------------------------------------------------
# LLM-grounded RCA
# ---------------------------------------------------------------------------

_RCA_SYSTEM_PROMPT = """\
You are a senior SRE performing a root cause analysis using the 5-Whys method.

Given:
- Incident metadata (id, category, priority, symptom, description)
- Evidence chunks from historical incidents and Jira issues (each with a citation_id)
- Triage result (severity, urgency, affected_service, suggested_team)

Produce a JSON object with EXACTLY these keys:
{
  "root_cause": "<one concise sentence>",
  "contributing_factors": [
    {"factor": "<description>", "evidence_id": "<citation_id or empty>", "confidence": <0.0-1.0>}
  ],
  "recommended_actions": ["<action 1>", "<action 2>"],
  "lessons_learned": ["<lesson 1>", "<lesson 2>"],
  "confidence": <overall float 0.0-1.0>,
  "evidence_ids": ["<citation_id>", ...]
}

Rules:
- Be specific. Reference evidence by citation_id where possible.
- Use 5-Whys reasoning: ask "why" at least 3 times before stating root cause.
- Do NOT invent facts not present in the evidence.
- Output ONLY the JSON object, no markdown fences.
"""


def generate_rca(
    incident_id: str,
    evidence_chunks: List[Dict[str, Any]],
    triage_result: Optional[Dict[str, Any]] = None,
    incident_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a structured RCA dict grounded on retrieved evidence.

    Tries Gemini LLM first; falls back to rules-based RCA if unavailable.

    Args:
        incident_id:     Incident identifier string.
        evidence_chunks: List of evidence dicts, each with 'citation_id', 'text'/'content',
                         'source', 'similarity_score'.
        triage_result:   Optional triage dict from Phase 2 (severity, urgency, team, …).
        incident_data:   Optional raw incident row dict.

    Returns:
        Dict with keys: root_cause, contributing_factors, recommended_actions,
                        lessons_learned, confidence, evidence_ids.
    """
    try:
        result = _llm_rca(incident_id, evidence_chunks, triage_result, incident_data)
        if result:
            logger.info("RCA generated via LLM for %s (confidence=%.2f)", incident_id, result.get("confidence", 0))
            return result
    except Exception as exc:
        logger.warning("LLM RCA failed for %s: %s — using rules fallback", incident_id, exc)

    return _rules_rca(incident_id, evidence_chunks, triage_result, incident_data)


def _llm_rca(
    incident_id: str,
    evidence_chunks: List[Dict[str, Any]],
    triage_result: Optional[Dict[str, Any]],
    incident_data: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Call Gemini to produce structured RCA JSON. Returns None on any failure."""
    import google.generativeai as genai

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    genai.configure(api_key=api_key)

    # Build user message
    evidence_text = "\n".join(
        f"[{e.get('citation_id', '?')}] ({e.get('source', '?')}, score={e.get('similarity_score', 0):.2f}): "
        f"{str(e.get('text') or e.get('content') or e.get('body') or '')[:300]}"
        for e in evidence_chunks[:10]
    )

    user_msg = (
        f"Incident ID: {incident_id}\n"
        f"Incident data: {json.dumps(incident_data or {}, default=str)[:500]}\n"
        f"Triage: {json.dumps(triage_result or {}, default=str)[:300]}\n\n"
        f"Evidence chunks:\n{evidence_text}"
    )

    model = genai.GenerativeModel(
        model_name=os.getenv("MODEL", "gemini-2.0-flash-001"),
        system_instruction=_RCA_SYSTEM_PROMPT,
    )
    response = model.generate_content(user_msg)
    raw = response.text.strip()

    # Strip markdown fences if model added them
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    parsed = json.loads(raw)
    return _validate_rca_structure(parsed)


def _rules_rca(
    incident_id: str,
    evidence_chunks: List[Dict[str, Any]],
    triage_result: Optional[Dict[str, Any]],
    incident_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Rules-based RCA fallback — no LLM required."""
    category = ""
    symptom = ""
    if incident_data:
        category = str(incident_data.get("category", ""))
        symptom = str(
            incident_data.get("symptom")
            or incident_data.get("u_symptom")
            or incident_data.get("description")
            or ""
        )
    if triage_result:
        category = category or str(triage_result.get("category", ""))

    combined_text = f"{category} {symptom} " + " ".join(
        str(e.get("text") or e.get("content") or "") for e in evidence_chunks[:5]
    )
    keywords = _keywords_from_text(combined_text)

    if keywords:
        primary_kw = keywords[0]
        root_cause = (
            f"The incident was caused by a {primary_kw}-related failure "
            f"in the {category or 'affected'} system."
        )
        factors = [
            {
                "factor": f"{kw.capitalize()} issue identified in evidence",
                "evidence_id": next(
                    (e.get("citation_id", "") for e in evidence_chunks if kw in str(e).lower()),
                    "",
                ),
                "confidence": 0.6,
            }
            for kw in keywords[:3]
        ]
    else:
        root_cause = (
            f"Root cause for incident {incident_id} could not be determined automatically. "
            "Manual investigation required."
        )
        factors = []

    evidence_ids = [
        e.get("citation_id", "") for e in evidence_chunks if e.get("citation_id")
    ][:5]

    return _validate_rca_structure({
        "root_cause": root_cause,
        "contributing_factors": factors,
        "recommended_actions": [],
        "lessons_learned": [],
        "confidence": 0.4 if keywords else 0.1,
        "evidence_ids": evidence_ids,
    })


def _validate_rca_structure(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all required keys are present with correct types."""
    return {
        "root_cause": str(raw.get("root_cause", "Unknown root cause")),
        "contributing_factors": list(raw.get("contributing_factors", [])),
        "recommended_actions": list(raw.get("recommended_actions", [])),
        "lessons_learned": list(raw.get("lessons_learned", [])),
        "confidence": float(raw.get("confidence", 0.0)),
        "evidence_ids": list(raw.get("evidence_ids", [])),
    }
