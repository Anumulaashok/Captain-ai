"""Agent code templates for AgentBuilder."""

AGENT_TEMPLATE = '''"""
{agent_name} Agent — {description}
"""
import logging
import time

from agents.base import AgentBase, AgentTask, AgentResult, Tool, Permission

log = logging.getLogger(__name__)


class Agent(AgentBase):
    id = "{agent_id}"
    name = "{agent_name} Agent"
    description = "{description}"
    capabilities = {capabilities}
    required_permissions = {permissions}
    required_integrations = {integrations}

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="execute_task",
                description="Execute the main task for this agent",
                parameters={{
                    "type": "object",
                    "properties": {{
                        "instruction": {{"type": "string", "description": "What to do"}},
                    }},
                    "required": ["instruction"],
                }},
                handler=self._execute_task,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()
        ok, missing = await self.check_integrations()
        if not ok:
            return self._integration_required_response(task, missing)

        tools = await self.get_tools()
        messages = [
            {{"role": "system", "content": "You are the {agent_name} agent. {description}"}},
            {{"role": "user", "content": task.user_message}},
        ]
        response, tool_calls, tokens = await self._llm_tool_loop(messages, tools, task)
        return AgentResult(
            task_id=task.id,
            success=bool(response),
            response=response or "Task completed.",
            tool_calls=tool_calls,
            tokens_used=tokens,
            latency_ms=int((time.time() - t_start) * 1000),
        )

    async def _execute_task(self, instruction: str) -> str:
        return f"Executed: {{instruction}}"
'''

INIT_TEMPLATE = "# {agent_id} agent package\n"
