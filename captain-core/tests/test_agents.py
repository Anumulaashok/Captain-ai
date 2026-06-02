"""Agent framework tests."""
import pytest
from agents.base import AgentTask, AgentResult, Tool, Permission, HealthStatus


def test_agent_task_auto_id():
    task = AgentTask(agent_id="coding", intent="coding_task", user_message="Write hello world")
    assert task.id != ""


def test_tool_ollama_format():
    tool = Tool(
        name="search_web",
        description="Search the web",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    fmt = tool.to_ollama_format()
    assert fmt["type"] == "function"
    assert fmt["function"]["name"] == "search_web"
    assert "query" in fmt["function"]["parameters"]["properties"]


def test_permission_values():
    assert Permission.FILESYSTEM_READ.value == "filesystem:read"
    assert Permission.TERMINAL_EXECUTE.value == "terminal:execute"


@pytest.mark.asyncio
async def test_coding_agent_health():
    from agents.coding.agent import Agent
    agent = Agent()
    status = await agent.health_check()
    assert status == HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_file_agent_safe_path():
    from agents.file.agent import Agent
    from pathlib import Path
    agent = Agent()
    home = Path.home()
    safe = agent._safe_path("~/Documents")
    assert str(safe).startswith(str(home))

    with pytest.raises(PermissionError):
        agent._safe_path("/etc/passwd")


@pytest.mark.asyncio
async def test_terminal_agent_blocked_commands():
    from agents.terminal.agent import Agent
    agent = Agent()
    result = await agent._run_command("rm -rf /tmp/test")
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_terminal_agent_safe_command():
    from agents.terminal.agent import Agent
    agent = Agent()
    result = await agent._run_command("echo hello")
    assert "hello" in result


@pytest.mark.asyncio
async def test_agent_registry_loads():
    from agents.registry import agent_registry
    all_agents = agent_registry.list_all()
    ids = [a.id for a in all_agents]
    assert "coding" in ids
    assert "file" in ids
    assert "terminal" in ids


@pytest.mark.asyncio
async def test_agent_registry_route():
    from agents.registry import agent_registry
    agents = agent_registry.route("coding_task")
    assert any(a.id == "coding" for a in agents)
