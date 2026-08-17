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
    required_integrations: list[str] = []  # e.g. ["gmail"]

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

    async def check_integrations(self) -> tuple[bool, list[str]]:
        """Check if all required integrations are connected."""
        from integrations.credentials import credentials_store
        missing = []
        for integration_id in self.required_integrations:
            if not await credentials_store.has_valid_token(integration_id):
                missing.append(integration_id)
        return len(missing) == 0, missing

    def _integration_required_response(
        self, task: AgentTask, missing: list[str]
    ) -> AgentResult:
        """Return a structured response prompting the user to connect integrations."""
        names = ", ".join(missing)
        artifacts = [
            Artifact(
                type="integration_prompt",
                name=mid,
                content=f"Connect {mid} in Settings > Integrations",
            )
            for mid in missing
        ]
        return AgentResult(
            task_id=task.id,
            success=False,
            response=(
                f"I need access to {names} to complete this task. "
                "Please connect in Settings > Integrations, then try again."
            ),
            error="integration_required",
            artifacts=artifacts,
        )

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

    @staticmethod
    def _looks_generic(text: str) -> bool:
        """True when the model gave a generic filler response instead of using tools."""
        if not text or len(text) > 400:
            return False
        markers = [
            "could you please provide",
            "please provide more details",
            "i'm here to assist",
            "how can i help",
            "i need more information",
            "could you clarify",
            "what would you like",
            "i'd be happy to help",
            "feel free to ask",
        ]
        low = text.lower()
        return any(m in low for m in markers)

    async def _llm_tool_loop(
        self,
        messages: list[dict],
        tools: list[Tool],
        task: AgentTask,
    ) -> tuple[str, list[ToolCall], int]:
        """
        Core ReAct loop. Two completely separate paths:
          1. Gemini  — native function calling (tool_calls format)
          2. Ollama  — text-based ReAct (plain conversation, no tool_calls messages)

        Returns (final_response, tool_calls, total_tokens).
        """
        from models.ollama_client import OllamaClient
        from models.gemini_client import gemini_client
        from models.router import model_router, ModelRole, INTENT_TO_ROLE
        from config import settings

        delegation_depth = task.context.get("_delegation_depth", 0) if task.context else 0
        delegate_tool = self._make_delegate_tool(task, delegation_depth)
        all_tools = list(tools) + ([delegate_tool] if delegate_tool else [])
        tool_map: dict[str, Tool] = {t.name: t for t in all_tools}
        formatted_tools = [t.to_ollama_format() for t in all_tools]

        model_override = task.context.get("model_override") if task.context else None
        use_gemini = (not model_override) and await gemini_client.is_configured()
        role = INTENT_TO_ROLE.get(task.intent, ModelRole.CHAT)
        ollama_model = model_override or await model_router.get_model_for_role(role)
        gemini_model = settings.gemini_model

        # ── shared: execute one tool call and return (record, result_str) ──
        async def _exec_tool(tool_name: str, args: dict) -> tuple[ToolCall, str]:
            record = ToolCall(tool_name=tool_name, arguments=args)
            t0 = time.time()
            try:
                tool = tool_map.get(tool_name)
                if not tool or not tool.handler:
                    raise ValueError(f"Unknown tool: {tool_name}")
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
                            raise PermissionError(f"Permission '{perm.value}' denied by user")
                result_str = str(await tool.handler(**args))
                record.result = result_str
            except Exception as e:
                result_str = f"Error: {e}"
                record.error = str(e)
                log.warning(f"Tool {tool_name} failed: {e}")
            record.duration_ms = int((time.time() - t0) * 1000)
            return record, result_str

        # ── PATH 1: Gemini native function calling ─────────────────────────
        if use_gemini:
            log.info(f"Agent '{self.id}' using Gemini ({gemini_model})")
            all_tool_calls: list[ToolCall] = []
            loop_messages = list(messages)
            try:
                for _ in range(task.max_iterations):
                    response = await gemini_client.chat_complete(
                        gemini_model, loop_messages, tools=formatted_tools, temperature=0.1
                    )
                    msg = response.get("message", {})
                    raw_calls = msg.get("tool_calls", [])
                    if not raw_calls:
                        return msg.get("content", ""), all_tool_calls, 0

                    tool_results = []
                    for tc in raw_calls:
                        fn = tc.get("function", {})
                        name = fn.get("name", "")
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {}
                        record, result_str = await _exec_tool(name, args)
                        all_tool_calls.append(record)
                        tool_results.append({"role": "tool", "content": result_str})

                    loop_messages.append({"role": "assistant", "content": "", "tool_calls": raw_calls})
                    loop_messages.extend(tool_results)
                return "Task completed.", all_tool_calls, 0

            except Exception as e:
                log.warning(f"Gemini failed ({e}), switching to Ollama text-tool mode")
                # fall through to Ollama path below

        # ── PATH 2: Ollama text-based ReAct ───────────────────────────────
        # Never sends tool_calls in messages — uses plain conversation throughout.
        log.info(f"Agent '{self.id}' using Ollama text-tool mode ({ollama_model})")
        ollama = OllamaClient()
        all_tool_calls = []

        # Build the tool-use system prompt once
        tool_sigs = "\n".join(
            f"  {t['function']['name']}:"
            f" {t['function']['description']}"
            f" | params: {list(t['function']['parameters'].get('properties', {}).keys())}"
            for t in formatted_tools
        )
        tool_select_prompt = (
            "You are an action-first assistant. Act immediately — do NOT ask for clarification.\n\n"
            f"Available tools:\n{tool_sigs}\n\n"
            "Reply with ONLY valid JSON on a single line, no explanation:\n"
            '{"tool": "<tool_name>", "args": {<param>: <value>}}\n\n'
            "Use the exact tool name from the list above."
        )

        def _inject_system(msgs: list[dict], extra: str) -> list[dict]:
            out = []
            done = False
            for m in msgs:
                if m["role"] == "system" and not done:
                    out.append({"role": "system", "content": extra + "\n\n" + m["content"]})
                    done = True
                else:
                    out.append(m)
            if not done:
                out.insert(0, {"role": "system", "content": extra})
            return out

        def _parse_tool_json(text: str) -> tuple[str, dict]:
            text = text.strip().strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
            # grab first JSON object in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end == 0:
                return "", {}
            try:
                data = json.loads(text[start:end])
                return data.get("tool", ""), data.get("args", {})
            except Exception:
                return "", {}

        # Carry conversation as plain text (assistant/user roles only — no tool_calls)
        convo = list(messages)

        for iteration in range(task.max_iterations):
            if not all_tool_calls or iteration == 0:
                # Ask model which tool to call
                patched = _inject_system(convo, tool_select_prompt)
                try:
                    resp = await ollama.chat_complete(ollama_model, patched, tools=None, temperature=0.0)
                except Exception as e:
                    log.error(f"Ollama call failed: {e}")
                    return f"Error: {e}", all_tool_calls, 0

                raw = resp.get("message", {}).get("content", "").strip()
                tool_name, args = _parse_tool_json(raw)

                if not tool_name or tool_name not in tool_map:
                    # Model gave a text answer or couldn't pick a tool
                    if all_tool_calls:
                        break   # already did work — ask for final answer below
                    if self._looks_generic(raw):
                        log.warning(f"Generic response on first turn, no tool parsed from: {raw[:80]}")
                        # pick the first tool automatically and infer args from the user message
                        tool_name = formatted_tools[0]["function"]["name"]
                        user_text = next((m["content"] for m in reversed(convo) if m["role"] == "user"), "")
                        args = {"query": user_text} if "query" in formatted_tools[0]["function"]["parameters"].get("properties", {}) else {}
                        log.info(f"Auto-selecting tool '{tool_name}' with inferred args")
                    else:
                        return raw, all_tool_calls, 0

                log.info(f"Text-tool call: {tool_name}({args})")
                record, result_str = await _exec_tool(tool_name, args)
                all_tool_calls.append(record)

                # Append as plain conversation — Ollama can read this fine
                convo.append({"role": "assistant", "content": f"[Used tool: {tool_name}]"})
                convo.append({
                    "role": "user",
                    "content": (
                        f"Tool result from {tool_name}:\n{result_str}\n\n"
                        "Now answer the original question directly and concisely based on this result. "
                        "Do not call another tool."
                    ),
                })
            else:
                # Ask for final answer using the tool results already in convo
                break

        # Final answer pass — plain generation, no tools
        final_prompt = _inject_system(convo, "Answer the user's question based on the tool results above. Be direct and specific.")
        try:
            resp = await ollama.chat_complete(ollama_model, final_prompt, tools=None, temperature=0.3)
            answer = resp.get("message", {}).get("content", "").strip()
        except Exception as e:
            answer = "\n\n".join(r.result or "" for r in all_tool_calls if r.result)
            if not answer:
                answer = f"Error getting final answer: {e}"

        return answer, all_tool_calls, 0
