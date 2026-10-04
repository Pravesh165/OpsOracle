"""Tests for opsmind/tools/rca.py and generate_postmortem_content — Phase 3."""
import asyncio
import os
import sys
import types as _types

import pytest

# ---------------------------------------------------------------------------
# Isolate from ADK import chain
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if "opsmind" not in sys.modules:
    _pkg = _types.ModuleType("opsmind")
    _pkg.__path__ = [os.path.join(_ROOT, "opsmind")]
    _pkg.__package__ = "opsmind"
    sys.modules["opsmind"] = _pkg

# Stub google.adk.tools.tool_context
_google = _types.ModuleType("google")
_google_adk = _types.ModuleType("google.adk")
_google_adk_tools = _types.ModuleType("google.adk.tools")
_google_adk_tools_tc = _types.ModuleType("google.adk.tools.tool_context")


class _FakeToolContext:
    def __init__(self):
        self.state: dict = {}


_google_adk_tools_tc.ToolContext = _FakeToolContext
sys.modules.setdefault("google", _google)
sys.modules.setdefault("google.adk", _google_adk)
sys.modules.setdefault("google.adk.tools", _google_adk_tools)
sys.modules.setdefault("google.adk.tools.tool_context", _google_adk_tools_tc)

# Stub opsmind.config
import logging as _logging
_cfg = _types.ModuleType("opsmind.config")
_cfg.logger = _logging.getLogger("test_rca")
_cfg.MODEL_NAME = "gemini-2.0-flash-001"
_cfg.OUTPUT_DIR = os.path.join(_ROOT, "output")
_cfg.GCP_STORAGE_ENABLED = False
sys.modules["opsmind.config"] = _cfg

# Stub opsmind.tools.guardrail
_guardrail_mod = _types.ModuleType("opsmind.tools.guardrail")
_guardrail_mod.with_guardrail = lambda fn: fn
_tools_pkg = _types.ModuleType("opsmind.tools")
_tools_pkg.__path__ = [os.path.join(_ROOT, "opsmind", "tools")]
_tools_pkg.__package__ = "opsmind.tools"
sys.modules["opsmind.tools"] = _tools_pkg
sys.modules["opsmind.tools.guardrail"] = _guardrail_mod

# Now import rca
from opsmind.tools.rca import (  # noqa: E402
    format_citations,
    generate_rca,
    extract_action_items,
    extract_lessons_learned,
    _rules_rca,
    _validate_rca_structure,
    _keywords_from_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _evidence(citation_id: str, source: str = "incident", text: str = "sample text", score: float = 0.8):
    return {"citation_id": citation_id, "source": source, "text": text, "similarity_score": score}


# ---------------------------------------------------------------------------
# format_citations
# ---------------------------------------------------------------------------

def test_format_citations_single():
    result = format_citations([_evidence("INC-0045")])
    assert result == "[INC-0045]"


def test_format_citations_multiple():
    result = format_citations([_evidence("INC-0045"), _evidence("JIRA-WW-712", "jira_issue")])
    assert "[INC-0045]" in result
    assert "[JIRA-WW-712]" in result


def test_format_citations_deduplicates():
    result = format_citations([_evidence("INC-0045"), _evidence("INC-0045")])
    assert result.count("[INC-0045]") == 1


def test_format_citations_empty_list():
    assert format_citations([]) == ""


def test_format_citations_skips_empty_ids():
    result = format_citations([{"citation_id": ""}, {"citation_id": "INC-001"}])
    assert result == "[INC-001]"


def test_format_citations_renders_brackets():
    """Roadmap acceptance: format_citations renders bracket notation."""
    evidence = [
        {"citation_id": "INC-0045"},
        {"citation_id": "JIRA-WW-712"},
    ]
    result = format_citations(evidence)
    assert result == "[INC-0045][JIRA-WW-712]"


# ---------------------------------------------------------------------------
# _validate_rca_structure
# ---------------------------------------------------------------------------

def test_validate_rca_structure_required_keys():
    result = _validate_rca_structure({})
    for key in ["root_cause", "contributing_factors", "recommended_actions",
                "lessons_learned", "confidence", "evidence_ids"]:
        assert key in result


def test_validate_rca_structure_types():
    result = _validate_rca_structure({
        "root_cause": "disk full",
        "contributing_factors": [{"factor": "log rotation disabled"}],
        "confidence": "0.7",
        "evidence_ids": ["INC-001"],
    })
    assert isinstance(result["root_cause"], str)
    assert isinstance(result["contributing_factors"], list)
    assert isinstance(result["confidence"], float)
    assert isinstance(result["evidence_ids"], list)


# ---------------------------------------------------------------------------
# _keywords_from_text
# ---------------------------------------------------------------------------

def test_keywords_from_text_detects_timeout():
    kws = _keywords_from_text("connection timeout exceeded")
    assert "timeout" in kws


def test_keywords_from_text_detects_memory():
    kws = _keywords_from_text("out of memory OOM killer")
    assert "memory" in kws


def test_keywords_from_text_empty():
    kws = _keywords_from_text("")
    assert isinstance(kws, list)


# ---------------------------------------------------------------------------
# generate_rca (rules fallback — no LLM key needed)
# ---------------------------------------------------------------------------

def test_generate_rca_returns_required_fields():
    evidence = [_evidence("INC-001", text="database connection timeout")]
    result = generate_rca("INC-001", evidence)
    for key in ["root_cause", "contributing_factors", "recommended_actions",
                "lessons_learned", "confidence", "evidence_ids"]:
        assert key in result, f"Missing key: {key}"


def test_generate_rca_root_cause_is_string():
    result = generate_rca("INC-002", [_evidence("INC-002", text="nginx 502 upstream timeout")])
    assert isinstance(result["root_cause"], str)
    assert len(result["root_cause"]) > 0


def test_generate_rca_confidence_in_range():
    result = generate_rca("INC-003", [_evidence("INC-003", text="redis memory eviction")])
    assert 0.0 <= result["confidence"] <= 1.0


def test_generate_rca_evidence_ids_populated():
    evidence = [_evidence("INC-004"), _evidence("JIRA-WW-100", "jira_issue")]
    result = generate_rca("INC-004", evidence)
    assert isinstance(result["evidence_ids"], list)


def test_generate_rca_with_triage_result():
    triage = {"severity": 0.95, "urgency": "CRITICAL", "category": "network", "suggested_team": "network-ops"}
    evidence = [_evidence("INC-005", text="network outage site down")]
    result = generate_rca("INC-005", evidence, triage_result=triage)
    assert result["root_cause"]


def test_generate_rca_with_incident_data():
    incident = {"category": "database", "u_symptom": "connection pool exhausted", "priority": "P1"}
    evidence = [_evidence("INC-006", text="database connection pool exhausted")]
    result = generate_rca("INC-006", evidence, incident_data=incident)
    assert "database" in result["root_cause"].lower() or result["confidence"] > 0


def test_generate_rca_empty_evidence_does_not_crash():
    result = generate_rca("INC-007", [])
    assert "root_cause" in result


# ---------------------------------------------------------------------------
# extract_action_items
# ---------------------------------------------------------------------------

def test_extract_action_items_returns_list():
    rca = generate_rca("INC-010", [_evidence("INC-010", text="timeout database")])
    items = extract_action_items(rca)
    assert isinstance(items, list)
    assert len(items) > 0


def test_extract_action_items_non_empty_always():
    """Even with empty RCA, must return at least one item (runbook fallback)."""
    items = extract_action_items({"root_cause": "", "contributing_factors": [],
                                  "recommended_actions": [], "lessons_learned": [],
                                  "confidence": 0.0, "evidence_ids": []})
    assert len(items) >= 1


def test_extract_action_items_uses_similar_resolutions():
    rca = {"root_cause": "nginx timeout", "contributing_factors": [],
           "recommended_actions": [], "lessons_learned": [],
           "confidence": 0.5, "evidence_ids": []}
    items = extract_action_items(rca, similar_resolutions=["increased nginx timeout"])
    assert any("nginx" in i.lower() or "timeout" in i.lower() for i in items)


def test_extract_action_items_includes_runbook():
    items = extract_action_items({"root_cause": "unknown", "contributing_factors": [],
                                  "recommended_actions": [], "lessons_learned": [],
                                  "confidence": 0.0, "evidence_ids": []})
    assert any("runbook" in i.lower() or "playbook" in i.lower() for i in items)


# ---------------------------------------------------------------------------
# extract_lessons_learned
# ---------------------------------------------------------------------------

def test_extract_lessons_learned_returns_list():
    rca = generate_rca("INC-020", [_evidence("INC-020", text="memory leak production")])
    lessons = extract_lessons_learned(rca)
    assert isinstance(lessons, list)
    assert len(lessons) > 0


def test_extract_lessons_learned_non_empty_always():
    lessons = extract_lessons_learned({"root_cause": "", "contributing_factors": [],
                                       "recommended_actions": [], "lessons_learned": [],
                                       "confidence": 0.0, "evidence_ids": []})
    assert len(lessons) >= 1


def test_extract_lessons_learned_uses_incident_data():
    rca = {"root_cause": "certificate expired", "contributing_factors": [],
           "recommended_actions": [], "lessons_learned": [],
           "confidence": 0.5, "evidence_ids": []}
    lessons = extract_lessons_learned(rca, incident_data={"description": "certificate expiry caused outage"})
    assert any("certificate" in l.lower() or "expir" in l.lower() for l in lessons)


# ---------------------------------------------------------------------------
# _rules_rca
# ---------------------------------------------------------------------------

def test_rules_rca_with_known_keyword():
    evidence = [_evidence("INC-030", text="redis out of memory eviction")]
    result = _rules_rca("INC-030", evidence, None, {"category": "database"})
    assert "redis" in result["root_cause"].lower() or "memory" in result["root_cause"].lower()


def test_rules_rca_unknown_keyword_fallback():
    evidence = [_evidence("INC-031", text="something completely unrelated xyz")]
    result = _rules_rca("INC-031", evidence, None, None)
    assert "root_cause" in result
    assert result["confidence"] < 0.5


# ---------------------------------------------------------------------------
# Postmortem integration (no ADK / no LLM — stubs context)
# ---------------------------------------------------------------------------

def test_postmortem_content_has_rca_section():
    """generate_postmortem_content must return content with an RCA section."""
    # Stub opsmind.context
    _ctx_mod = _types.ModuleType("opsmind.context")

    async def _fake_get_incident_context(tc, query):
        return {
            "status": "success",
            "context": [
                {
                    "type": "incident", "id": "INC0000001",
                    "citation_id": "INC-0000001",
                    "similarity_score": 0.9,
                    "category": "network", "priority": "P1",
                    "state": "Resolved",
                    "short_description": "Network outage",
                    "symptom": "site down",
                    "description": "nginx upstream timeout caused 502 errors",
                    "resolution": "Restarted nginx",
                },
                {
                    "type": "jira_issue", "id": "WW-100",
                    "citation_id": "JIRA-WW-100",
                    "similarity_score": 0.7,
                    "key": "WW-100",
                    "summary": "Nginx timeout config",
                    "status.name": "Resolved",
                    "priority.name": "High",
                },
            ],
        }

    _ctx_mod.get_incident_context = _fake_get_incident_context
    sys.modules["opsmind.context"] = _ctx_mod

    # Also stub opsmind.utils (needed by postmortems.py imports)
    _utils_mod = _types.ModuleType("opsmind.utils")
    _utils_mod.upload_file_to_gcp = lambda **kw: {"status": "error", "message": "stub"}
    _utils_mod.generate_download_link = lambda **kw: {"status": "error", "message": "stub"}
    _utils_mod.list_postmortem_files_in_gcp = lambda: {"status": "error", "message": "stub"}
    sys.modules["opsmind.utils"] = _utils_mod

    # Force re-import of postmortems with stubs in place
    if "opsmind.tools.postmortems" in sys.modules:
        del sys.modules["opsmind.tools.postmortems"]
    if "opsmind.tools.rca" in sys.modules:
        del sys.modules["opsmind.tools.rca"]

    from opsmind.tools.postmortems import generate_postmortem_content

    tc = _FakeToolContext()
    result = run(generate_postmortem_content(tc, "INC0000001"))

    assert result["status"] == "success", result.get("message")
    content = result["content"]
    assert "Root Cause" in content
    assert "INC0000001" in content


def test_postmortem_content_contains_citation():
    """Postmortem must contain at least one [INC-*] or [JIRA-*] citation."""
    from opsmind.tools.postmortems import generate_postmortem_content

    tc = _FakeToolContext()
    result = run(generate_postmortem_content(tc, "INC0000001"))
    content = result.get("content", "")
    import re
    citations = re.findall(r"\[(?:INC|JIRA)-[^\]]+\]", content)
    assert len(citations) >= 1, f"No citations found in postmortem. Content snippet: {content[:500]}"


def test_postmortem_result_has_rca_key():
    """Result dict must include 'rca' key with required fields."""
    from opsmind.tools.postmortems import generate_postmortem_content

    tc = _FakeToolContext()
    result = run(generate_postmortem_content(tc, "INC0000001"))
    assert "rca" in result
    rca = result["rca"]
    assert "root_cause" in rca
    assert "confidence" in rca


def test_postmortem_result_has_citations_key():
    from opsmind.tools.postmortems import generate_postmortem_content

    tc = _FakeToolContext()
    result = run(generate_postmortem_content(tc, "INC0000001"))
    assert "citations" in result
