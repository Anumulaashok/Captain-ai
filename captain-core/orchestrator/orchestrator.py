"""Central Orchestrator — routes messages to the right model and agent."""
import asyncio
import logging
import time
from collections.abc import AsyncGenerator

from orchestrator.intent import classify_intent
from memory.manager import memory_manager
from agents.registry import agent_registry
from agents.base import AgentTask
from models.router import model_router, ModelRole, INTENT_TO_ROLE

log = logging.getLogger(__name__)


class Orchestrator:

    async def process(
        self,
        user_message: str,
        conversation_id: str,
    ) -> AsyncGenerator[dict, None]:
        """
        Main entry point. Yields SSE event dicts:
          {"type": "token",          "data": {"text": str, "done": bool}}
          {"type": "model_used",     "data": {"role": str, "model": str}}
          {"type": "agent_started",  "data": {"agent_id": str, "agent_name": str}}
          {"type": "agent_finished", "data": {...}}
          {"type": "memory_stored",  "data": {...}}
        """
        t_start = time.time()
        await memory_manager.episodic.add_message(conversation_id, "user", user_message)

        # Classify intent using the FAST model (cheap, quick)
        intent = await classify_intent(user_message)
        log.info(f"Intent: {intent.intent} ({intent.confidence:.2f})")

        full_response = ""

        if intent.intent == "simple_chat" or intent.confidence < 0.6:
            async for event in self._llm_chat(user_message, conversation_id, intent.intent):
                if event["type"] == "token":
                    full_response += event["data"].get("text", "")
                yield event
        else:
            agents = agent_registry.route(intent.intent)
            enabled_agents = await self._filter_enabled(agents)

            if not enabled_agents:
                async for event in self._llm_chat(user_message, conversation_id, intent.intent):
                    if event["type"] == "token":
                        full_response += event["data"].get("text", "")
                    yield event
            else:
                agent = enabled_agents[0]
                # Tell the agent which model to use for its role
                role_model = await model_router.get_model_for_intent(intent.intent)
                yield {"type": "agent_started", "data": {
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "model": role_model,
                }}
                yield {"type": "model_used", "data": {
                    "role": INTENT_TO_ROLE.get(intent.intent, ModelRole.CHAT).value,
                    "model": role_model,
                }}

                task = AgentTask(
                    agent_id=agent.id,
                    intent=intent.intent,
                    user_message=user_message,
                    context={"model_override": role_model},
                )

                try:
                    result = await agent.run(task)
                    full_response = result.response
                    yield {"type": "agent_finished", "data": {
                        "agent_id": agent.id,
                        "task_id": task.id,
                        "success": result.success,
                        "tool_calls": len(result.tool_calls),
                        "artifacts": [a.model_dump() for a in result.artifacts],
                        "latency_ms": result.latency_ms,
                    }}
                    # Stream agent response as tokens
                    for i, word in enumerate(full_response.split(" ")):
                        done = i == len(full_response.split(" ")) - 1
                        yield {"type": "token", "data": {"text": word + ("" if done else " "), "done": done}}
                        await asyncio.sleep(0)
                except Exception as e:
                    log.error(f"Agent {agent.id} failed: {e}")
                    full_response = f"The {agent.name} encountered an error: {e}"
                    yield {"type": "token", "data": {"text": full_response, "done": True}}

        # Persist assistant response
        latency_ms = int((time.time() - t_start) * 1000)
        await memory_manager.episodic.add_message(
            conversation_id, "assistant", full_response, latency_ms=latency_ms
        )

        # Auto-consolidate memory
        prefs = await memory_manager.preferences.get_all()
        if prefs.get("memory_auto_consolidate", True):
            msgs = await memory_manager.episodic.get_recent_messages(conversation_id)
            threshold = int(prefs.get("memory_consolidate_after_n", 10))
            if len(msgs) >= threshold and len(msgs) % threshold == 0:
                asyncio.create_task(memory_manager.consolidate(conversation_id))
                yield {"type": "memory_stored", "data": {"status": "consolidating"}}

    async def _llm_chat(
        self, user_message: str, conversation_id: str, intent: str
    ) -> AsyncGenerator[dict, None]:
        """Direct LLM response using the role-appropriate model."""
        from models.ollama_client import OllamaClient

        ollama = OllamaClient()
        if not await ollama.is_running():
            yield {"type": "token", "data": {
                "text": "⚠️ Ollama is not running. Start it with: `brew services start ollama`",
                "done": True,
            }}
            return

        # Pick model by role
        role = INTENT_TO_ROLE.get(intent, ModelRole.CHAT)
        model = await model_router.get_model_for_role(role)

        # Verify model is actually available (router falls back, but double-check)
        local = await ollama.list_local()
        if not local:
            yield {"type": "token", "data": {
                "text": (
                    "⚠️ No models downloaded yet.\n\n"
                    "Go to the **Models** page and download a model first.\n"
                    "Recommended: **Qwen 2.5 7B** (4.7 GB) or **Gemma 2 2B** (2.7 GB, fastest)."
                ),
                "done": True,
            }}
            return

        yield {"type": "model_used", "data": {"role": role.value, "model": model}}

        context = await memory_manager.retrieve_context(user_message, conversation_id)
        messages = memory_manager.build_messages(context, user_message)

        log.info(f"Chat using model: {model} (role: {role.value})")
        try:
            async for token in ollama.chat(model, messages):
                yield {"type": "token", "data": {"text": token, "done": False}}
            yield {"type": "token", "data": {"text": "", "done": True}}
        except Exception as e:
            log.error(f"Chat error with {model}: {e}")
            yield {"type": "token", "data": {
                "text": f"⚠️ Error with model `{model}`: {e}",
                "done": True,
            }}

    async def _filter_enabled(self, agents) -> list:
        from db.database import AsyncSessionLocal
        from db.models import AgentRecord
        enabled = []
        for agent in agents:
            async with AsyncSessionLocal() as db:
                rec = await db.get(AgentRecord, agent.id)
            if rec and rec.is_enabled:
                enabled.append(agent)
        return enabled


orchestrator = Orchestrator()
