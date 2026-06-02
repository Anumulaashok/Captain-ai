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
        tool_map: dict[str, Tool] = {t.name: t for t in tools}
        ollama_tools = [t.to_ollama_format() for t in tools]
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
