"""
Shared pytest fixtures and test lifecycle hooks for OPS-Mind.
Ensures clean test isolation and event loop availability on all Python/OS runtimes.
"""

import asyncio
import os
import sys
import types as _types
import pytest

_ROOT = os.path.dirname(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Universally stub google.adk so all tests can run seamlessly
_google = _types.ModuleType("google")
_google.__path__ = []
_google_adk = _types.ModuleType("google.adk")
_google_adk.__path__ = []
_google_adk_agents = _types.ModuleType("google.adk.agents")
_google_adk_tools = _types.ModuleType("google.adk.tools")
_google_adk_tools.__path__ = []
_google_adk_tools_tc = _types.ModuleType("google.adk.tools.tool_context")
_google_adk_agent_tool = _types.ModuleType("google.adk.tools.agent_tool")
_google_genai = _types.ModuleType("google.genai")
_google_genai.__path__ = []
_google_genai_types = _types.ModuleType("google.genai.types")


class _MockAgent:
    def __init__(self, *a, **kw):
        self.name = kw.get("name", "mock_agent")


class _MockAgentTool:
    def __init__(self, *a, **kw):
        pass


class _FakeTC:
    def __init__(self, *a, **kw):
        self.state = {}


_google_adk_agents.Agent = _MockAgent
_google_adk_agents.SequentialAgent = _MockAgent
_google_adk_tools_tc.ToolContext = _FakeTC
_google_adk_agent_tool.AgentTool = _MockAgentTool
_google_adk.Agent = _MockAgent
_google_genai_types.GenerateContentConfig = dict

sys.modules.setdefault("google", _google)
sys.modules.setdefault("google.adk", _google_adk)
sys.modules.setdefault("google.adk.agents", _google_adk_agents)
sys.modules.setdefault("google.adk.tools", _google_adk_tools)
sys.modules.setdefault("google.adk.tools.tool_context", _google_adk_tools_tc)
sys.modules.setdefault("google.adk.tools.agent_tool", _google_adk_agent_tool)
sys.modules.setdefault("google.genai", _google_genai)
sys.modules.setdefault("google.genai.types", _google_genai_types)

# Eagerly import real opsmind.utils and opsmind.tools so stub modules in isolated tests do not corrupt full-suite imports
import opsmind.utils  # noqa: F401
import opsmind.tools  # noqa: F401
import opsmind.tools.guardrail  # noqa: F401


@pytest.fixture(autouse=True)
def ensure_event_loop():
    """Ensure an active event loop exists on current thread for run_until_complete."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    yield loop


class FakeToolContext:
    def __init__(self, session_id: str = "test-session-001"):
        self.state = {"session_id": session_id}


@pytest.fixture
def fake_tool_context():
    return FakeToolContext()


@pytest.fixture
def sample_incident():
    return {
        "number": "INC0000001",
        "priority": "P1",
        "category": "network",
        "cmdb_ci": "order-gateway",
        "symptom": "Upstream timeout 504 on primary API edge gateway",
        "description": "Critical outage affecting customer checkout traffic",
    }


@pytest.fixture
def sample_jira_issue():
    return {
        "id": "10001",
        "key": "OPS-10001",
        "summary": "Nginx upstream timeout in order gateway",
        "description": "Increase proxy_read_timeout and reload service",
        "status": {"name": "In Progress"},
        "priority": {"name": "Highest"},
    }
