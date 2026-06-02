"""Agent base class — all agents inherit from AgentBase."""
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable
from pydantic import BaseModel

log = logging.getLogger(__name__)


class Permission(str, Enum):
    FILESYSTEM_READ  = "filesystem:read"
    FILESYSTEM_WRITE = "filesystem:write"
    NETWORK_FETCH    = "network:fetch"
    EMAIL_READ       = "email:read"
    EMAIL_WRITE      = "email:write"
    CALENDAR_READ    = "calendar:read"
    CALENDAR_WRITE   = "calendar:write"
    TERMINAL_EXECUTE = "terminal:execute"
    BROWSER_OPEN     = "browser:open"


class HealthStatus(str, Enum):
    HEALTHY   = "healthy"
    DEGRADED  = "degraded"
    UNHEALTHY = "unhealthy"


class Tool(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Any = None  # Callable, excluded from serialization

    model_config = {"arbitrary_types_allowed": True}

    def to_ollama_format(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Artifact(BaseModel):
    type: str         # code | file | url | data | image
    name: str
    content: str
    mime_type: str | None = None
    path: str | None = None


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict
    result: str | None = None
    error: str | None = None
    duration_ms: int | None = None


class AgentTask(BaseModel):
    id: str = ""
    agent_id: str
    intent: str
    user_message: str
    context: dict = {}
    max_iterations: int = 10

    def __init__(self, **data):
        if not data.get("id"):
            data["id"] = str(uuid.uuid4())
        super().__init__(**data)


class AgentResult(BaseModel):
    task_id: str
    success: bool
    response: str
    artifacts: list[Artifact] = []
    tool_calls: list[ToolCall] = []
    tokens_used: int = 0
    latency_ms: int = 0
    error: str | None = None


class AgentBase(ABC):
    id: str = ""
    name: str = ""
    description: str = ""
    capabilities: list[str] = []
    required_permissions: list[Permission] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    @abstractmethod
    async def run(self, task: AgentTask) -> AgentResult:
        ...

    @abstractmethod
    async def get_tools(self) -> list[Tool]:
        ...

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    async def validate_permissions(self) -> bool:
        from security.permissions import permission_manager
        for perm in self.required_permissions:
            if not await permission_manager.has_permission(self.id, perm):
                return False
        return True

    def _make_delegate_tool(self, task: AgentTask, delegation_depth: int) -> Tool | None:
        """
        Build a 'delegate_to_agent' tool that lets the LLM hand a subtask to another agent.
        Only injected when the task is explicitly from a multi-agent orchestration context
        AND we haven't hit the max delegation depth.
        """
        MAX_DEPTH = 2
        # Only add delegation in multi-agent contexts — not for every single-agent task
        is_multi_agent = task.context.get("source") == "multi_agent" or delegation_depth > 0
        if not is_multi_agent or delegation_depth >= MAX_DEPTH:
            return None

        async def _delegate(agent_id: str, instruction: str) -> str:
            from agents.registry import agent_registry
            target = agent_registry.get(agent_id)
            if not target:
                return f"Error: agent '{agent_id}' does not exist."
            sub_task = AgentTask(
                agent_id=agent_id,
                intent=f"{agent_id}_task",
                user_message=instruction,
                context={**task.context, "_delegation_depth": delegation_depth + 1},
                max_iterations=task.max_iterations,
            )
            result = await target.run(sub_task)
            return result.response if result.success else f"Delegation failed: {result.error}"

        from agents.registry import agent_registry
        available = [a.id for a in agent_registry.list_all() if a.id != self.id]
        # Note: no "enum" here — Ollama rejects JSON Schema enum in tool parameters.
        return Tool(
            name="delegate_to_agent",
            description=(
                f"Delegate a subtask to another specialized agent. "
                f"Available agent IDs: {', '.join(available)}. "
                "Use the exact agent_id string from this list."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": f"ID of the target agent. One of: {', '.join(available)}",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "Clear, self-contained instruction for the target agent",
                    },
                },
                "required": ["agent_id", "instruction"],
            },
            handler=_delegate,
        )

    async def _llm_tool_loop(
        self,
        messages: list[dict],
        tools: list[Tool],
        task: AgentTask,
    ) -> tuple[str, list[ToolCall], int]:
        """
        Core ReAct loop: LLM decides which tools to call, executes them,
        feeds results back, repeats until done or max_iterations.
        Returns (final_response, tool_calls, total_tokens).
        """
        from models.ollama_client import OllamaClient
        from models.router import model_router, ModelRole, INTENT_TO_ROLE

        ollama = OllamaClient()

        # Inject delegation tool so agents can hand subtasks to each other
        delegation_depth = task.context.get("_delegation_depth", 0) if task.context else 0
        delegate_tool = self._make_delegate_tool(task, delegation_depth)
        all_tools = list(tools) + ([delegate_tool] if delegate_tool else [])

        tool_map: dict[str, Tool] = {t.name: t for t in all_tools}
        ollama_tools = [t.to_ollama_format() for t in all_tools]
        all_tool_calls: list[ToolCall] = []
        total_tokens = 0
        loop_messages = list(messages)

        # Use role-appropriate model, or model_override from task context
        model_override = task.context.get("model_override") if task.context else None
        if model_override:
            model = model_override
        else:
            role = INTENT_TO_ROLE.get(task.intent, ModelRole.CHAT)
            model = await model_router.get_model_for_role(role)

        for iteration in range(task.max_iterations):
            response = await ollama.chat_complete(
                model,
                loop_messages,
                tools=ollama_tools,
                temperature=0.1,
            )

            msg = response.get("message", {})
            tool_calls_raw = msg.get("tool_calls", [])

            if not tool_calls_raw:
                return msg.get("content", ""), all_tool_calls, total_tokens

            # Execute each tool call
            tool_results = []
            for tc in tool_calls_raw:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}

                tool_record = ToolCall(tool_name=tool_name, arguments=args)
                t_start = time.time()

                try:
                    tool = tool_map.get(tool_name)
                    if not tool or not tool.handler:
                        raise ValueError(f"Unknown tool: {tool_name}")

                    # Check required permissions before executing; if missing, ask user
                    from security.permissions import permission_manager
                    from security.approvals import approval_manager
                    for perm in self.required_permissions:
                        if not await permission_manager.has_permission(self.id, perm):
                            approved = await approval_manager.request(
                                agent_id=self.id,
                                permission=perm.value,
                                reason=f"Running tool '{tool_name}'",
                            )
                            if approved:
                                await permission_manager.grant(self.id, perm)
                            else:
                                raise PermissionError(
                                    f"Permission '{perm.value}' denied by user"
                                )

                    result = await tool.handler(**args)
                    result_str = str(result)
                    tool_record.result = result_str
                except Exception as e:
                    result_str = f"Error: {e}"
                    tool_record.error = str(e)
                    log.warning(f"Tool {tool_name} failed: {e}")

                tool_record.duration_ms = int((time.time() - t_start) * 1000)
                all_tool_calls.append(tool_record)
                tool_results.append({"role": "tool", "content": result_str})

            # Add assistant message + tool results to loop
            loop_messages.append({"role": "assistant", "content": "", "tool_calls": tool_calls_raw})
            loop_messages.extend(tool_results)

        return "Task completed.", all_tool_calls, total_tokens
