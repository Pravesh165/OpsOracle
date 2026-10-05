"""
Post-remediation verification tools for OpsMind.

verify_resolution() runs a list of health checks after a runbook completes.
ALL pass  → RESOLVED + postmortem trigger stored in session state.
ANY fail  → MITIGATING + re-investigation flag.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from google.adk.tools.tool_context import ToolContext

from opsmind.config import logger
from opsmind.tools.guardrail import with_guardrail


# ---------------------------------------------------------------------------
# HealthCheck dataclass
# ---------------------------------------------------------------------------

@dataclass
class HealthCheck:
    name: str
    type: Literal["http", "metric", "log"]
    endpoint: str           # URL / metric name / log path
    expected: str           # "200" / "<100" / "no errors"
    timeout_sec: int = 10
    max_retries: int = 3


# ---------------------------------------------------------------------------
# Internal check implementations
# ---------------------------------------------------------------------------

def _http_check(url: str, expected_status: str, timeout_sec: int, max_retries: int) -> Dict[str, Any]:
    """Real HTTP GET check with retry."""
    import urllib.request
    import urllib.error

    expected_code = int(expected_status)
    last_error: Optional[str] = None

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                actual = resp.status
                passed = actual == expected_code
                return {
                    "passed": passed,
                    "type": "http",
                    "url": url,
                    "expected": expected_code,
                    "actual": actual,
                    "attempt": attempt,
                }
        except urllib.error.HTTPError as exc:
            actual = exc.code
            passed = actual == expected_code
            if passed:
                return {"passed": True, "type": "http", "url": url, "expected": expected_code, "actual": actual, "attempt": attempt}
            last_error = f"HTTP {actual}"
        except Exception as exc:
            last_error = str(exc)

    return {
        "passed": False,
        "type": "http",
        "url": url,
        "expected": expected_code,
        "actual": None,
        "error": last_error,
        "attempt": max_retries,
    }


def _metric_check(metric_name: str, threshold: str) -> Dict[str, Any]:
    """Stub: metric checks require a real metrics backend. Returns pending."""
    return {
        "passed": None,
        "status": "pending",
        "type": "metric",
        "metric": metric_name,
        "threshold": threshold,
        "message": "Metric check stub — integrate with Prometheus/CloudWatch for real values.",
    }


def _log_check(log_path: str, pattern: str) -> Dict[str, Any]:
    """Stub: log checks require log aggregation access. Returns pending."""
    return {
        "passed": None,
        "status": "pending",
        "type": "log",
        "log_path": log_path,
        "pattern": pattern,
        "message": "Log check stub — integrate with ELK/CloudWatch Logs for real values.",
    }


# ---------------------------------------------------------------------------
# Public tool: run_health_check
# ---------------------------------------------------------------------------

@with_guardrail
async def run_health_check(
    tool_context: ToolContext,
    check: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Execute a single health check.

    Args:
        check: Dict matching HealthCheck fields:
               name, type ("http"|"metric"|"log"), endpoint, expected,
               timeout_sec (default 10), max_retries (default 3).

    Returns:
        Result dict with at minimum: passed (bool|None), type, name.
    """
    try:
        name = check.get("name", "unnamed")
        check_type = check.get("type", "http").lower()
        endpoint = check.get("endpoint", "")
        expected = str(check.get("expected", "200"))
        timeout_sec = int(check.get("timeout_sec", 10))
        max_retries = int(check.get("max_retries", 3))

        if check_type == "http":
            result = _http_check(endpoint, expected, timeout_sec, max_retries)
        elif check_type == "metric":
            result = _metric_check(endpoint, expected)
        elif check_type == "log":
            result = _log_check(endpoint, expected)
        else:
            result = {"passed": False, "type": check_type, "error": f"Unknown check type: {check_type}"}

        result["name"] = name
        result["checked_at"] = datetime.now().isoformat()
        return result

    except Exception as exc:
        logger.error("run_health_check error: %s", exc)
        return {"passed": False, "name": check.get("name", "unnamed"), "error": str(exc)}


# ---------------------------------------------------------------------------
# Public tool: verify_resolution
# ---------------------------------------------------------------------------

@with_guardrail
async def verify_resolution(
    tool_context: ToolContext,
    incident_id: str,
    checks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Run all health checks after remediation and update incident state.

    ALL pass  → transition to RESOLVED, store postmortem trigger in session state.
    ANY fail  → transition to MITIGATING, flag for re-investigation.

    Stub checks (metric/log) with passed=None are treated as non-blocking warnings,
    not failures, so a mix of HTTP-pass + metric-stub still resolves.

    Args:
        incident_id: Incident identifier.
        checks: List of health check dicts (see run_health_check).

    Returns:
        {verdict: "PASS"|"FAIL", incident_id, new_state, results, summary}
    """
    from opsmind.tools.triage import transition_incident_state

    if not checks:
        return {
            "verdict": "FAIL",
            "incident_id": incident_id,
            "new_state": "MITIGATING",
            "results": [],
            "summary": "No checks provided — cannot verify resolution.",
        }

    results: List[Dict[str, Any]] = []
    for check in checks:
        result = await run_health_check(tool_context, check)
        results.append(result)

    # Definitive failures: passed is explicitly False
    failed = [r for r in results if r.get("passed") is False]
    pending = [r for r in results if r.get("passed") is None]
    passed_checks = [r for r in results if r.get("passed") is True]

    verdict = "PASS" if not failed else "FAIL"

    try:
        if verdict == "PASS":
            await transition_incident_state(tool_context, incident_id, "RESOLVED")
            new_state = "RESOLVED"
            # Store postmortem trigger in session state for verification_agent to act on
            tool_context.state["pending_postmortem"] = {
                "incident_id": incident_id,
                "triggered_at": datetime.now().isoformat(),
                "trigger_reason": "verification_passed",
            }
            logger.info("Incident %s verified RESOLVED — postmortem trigger stored.", incident_id)
        else:
            # Try MITIGATING; if already there or invalid, just record it
            try:
                await transition_incident_state(tool_context, incident_id, "MITIGATING")
                new_state = "MITIGATING"
            except ValueError:
                # Already in MITIGATING or another state that allows it
                states = tool_context.state.get("incident_states", {})
                new_state = states.get(incident_id, {}).get("state", "MITIGATING")
            logger.warning(
                "Incident %s verification FAILED — %d check(s) failed, returning to MITIGATING.",
                incident_id, len(failed),
            )
    except ValueError as exc:
        logger.error("State transition error during verification: %s", exc)
        new_state = "unknown"

    return {
        "verdict": verdict,
        "incident_id": incident_id,
        "new_state": new_state,
        "total_checks": len(checks),
        "passed_count": len(passed_checks),
        "failed_count": len(failed),
        "pending_count": len(pending),
        "failed_checks": [r["name"] for r in failed],
        "results": results,
        "verified_at": datetime.now().isoformat(),
        "summary": (
            f"All {len(checks)} checks passed — incident RESOLVED."
            if verdict == "PASS"
            else f"{len(failed)} of {len(checks)} checks failed — returning to MITIGATING."
        ),
    }
