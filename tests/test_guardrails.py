"""
Tests for Guardrail Safety Framework.
Verifies argument inspection, input validation, rate limiting, and health checks.
"""

import asyncio
import pytest
import opsmind.tools  # ensure package imported first
from opsmind.core.safety.framework import (
    GuardrailManager,
    GuardrailConfig,
    GuardrailType,
    ValidationGuardrail,
    RateLimitGuardrail,
    GuardrailStatus,
)
from opsmind.tools import (
    with_guardrail,
    check_guardrails_health,
)
import opsmind.tools.guardrail as _gr_impl
get_system_resources = getattr(_gr_impl, "get_system_resources", None)
if get_system_resources is None:
    from opsmind.tools.guardrail import get_system_resources


class FakeToolContext:
    def __init__(self):
        self.state = {}


def test_validation_guardrail_blocks_xss():
    cfg = GuardrailConfig(
        name="test_val",
        type=GuardrailType.VALIDATION,
        strict_mode=True,
    )
    guardrail = ValidationGuardrail(cfg)

    # Clean input
    clean_res = asyncio.run(guardrail.check({"data": {"msg": "normal logs"}}))
    assert clean_res.status == GuardrailStatus.PASSED

    # Malicious input
    xss_res = asyncio.run(guardrail.check({"data": {"msg": "alert(<script>bad</script>)"}}))
    assert clean_res.status == GuardrailStatus.PASSED
    assert xss_res.status == GuardrailStatus.FAILED
    assert "forbidden pattern" in xss_res.message


def test_rate_limit_guardrail_triggers():
    cfg = GuardrailConfig(
        name="test_rate",
        type=GuardrailType.RATE_LIMITING,
        strict_mode=False,
        custom_params={"max_requests": 2, "time_window": 60}
    )
    guardrail = RateLimitGuardrail(cfg)

    res1 = asyncio.run(guardrail.check({}))
    res2 = asyncio.run(guardrail.check({}))
    res3 = asyncio.run(guardrail.check({}))

    assert res1.status == GuardrailStatus.PASSED
    assert res2.status == GuardrailStatus.PASSED
    assert res3.status == GuardrailStatus.FAILED
    assert "Rate limit exceeded" in res3.message


def test_with_guardrail_inspects_positional_and_kwargs():
    @with_guardrail
    async def sample_op(tool_context, search_query: str):
        return {"status": "success", "query": search_query}

    ctx = FakeToolContext()

    # Clean call passes
    clean_out = asyncio.run(sample_op(ctx, search_query="kubernetes cluster"))
    assert clean_out["status"] == "success"

    # Malicious parameter triggers block
    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(sample_op(ctx, search_query="<script>bad</script>"))
    assert "Guardrails blocked execution" in str(exc_info.value)


def test_check_guardrails_health_and_system_resources():
    ctx = FakeToolContext()
    health = check_guardrails_health(ctx)
    assert health["status"] == "success"
    assert "enabled_guardrails" in health

    resources = get_system_resources(ctx)
    assert resources["status"] == "success"
    assert "resources" in resources

