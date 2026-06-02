"""Central Orchestrator — processes user messages end-to-end."""
import asyncio
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from orchestrator.intent import classify_intent, IntentResult
from memory.manager import memory_manager
from agents.registry import agent_registry
from agents.base import AgentTask

log = logging.getLogger(__name__)


class Orchestrator:

    async def process(
        self,
        user_message: str,
        conversation_id: str,
    ) -> AsyncGenerator[dict, None]:
        """
        Main entry point. Yields event dicts:
          {"type": "token", "data": {"text": "...", "done": bool}}
          {"type": "agent_started", "data": {...}}
          {"type": "agent_finished", "data": {...}}
          {"type": "memory_stored", "data": {...}}
        """
        t_start = time.time()

        # 1. Store user message
        await memory_manager.episodic.add_message(conversation_id, "user", user_message)

        # 2. Classify intent
        intent = await classify_intent(user_message)
        log.info(f"Intent: {intent.intent} ({intent.confidence:.2f})")

        full_response = ""

        if intent.intent == "simple_chat" or intent.confidence < 0.6:
            # Direct LLM response
            async for event in self._simple_chat(user_message, conversation_id):
                if event["type"] == "token":
                    full_response += event["data"].get("text", "")
                yield event
        else:
            # Route to agent(s)
            agents = agent_registry.route(intent.intent)
            enabled_agents = []
            for agent in agents:
                from db.database import AsyncSessionLocal
                from db.models import AgentRecord
                async with AsyncSessionLocal() as db:
                    rec = await db.get(AgentRecord, agent.id)
                if rec and rec.is_enabled:
                    enabled_agents.append(agent)

            if not enabled_agents:
                # Fall back to simple chat if no agents are enabled
                async for event in self._simple_chat(user_message, conversation_id):
                    if event["type"] == "token":
                        full_response += event["data"].get("text", "")
                    yield event
            else:
                # Run first matching agent (multi-agent: run sequentially for now)
                agent = enabled_agents[0]
                yield {
                    "type": "agent_started",
                    "data": {"agent_id": agent.id, "agent_name": agent.name},
                }

                task = AgentTask(
                    agent_id=agent.id,
                    intent=intent.intent,
                    user_message=user_message,
                )

                try:
                    result = await agent.run(task)
                    full_response = result.response

                    yield {
                        "type": "agent_finished",
                        "data": {
                            "agent_id": agent.id,
                            "task_id": task.id,
                            "success": result.success,
                            "tool_calls": len(result.tool_calls),
                            "artifacts": [a.dict() for a in result.artifacts],
                            "latency_ms": result.latency_ms,
                        },
                    }

                    # Stream the response tokens
                    words = full_response.split(" ")
                    for i, word in enumerate(words):
                        done = (i == len(words) - 1)
                        yield {"type": "token", "data": {"text": word + (" " if not done else ""), "done": done}}
                        await asyncio.sleep(0)

                except Exception as e:
                    log.error(f"Agent {agent.id} failed: {e}")
                    full_response = f"The {agent.name} encountered an error: {e}"
                    yield {"type": "token", "data": {"text": full_response, "done": True}}

        # 3. Store assistant response
        latency_ms = int((time.time() - t_start) * 1000)
        await memory_manager.episodic.add_message(
            conversation_id, "assistant", full_response, latency_ms=latency_ms
        )

        # 4. Auto-consolidate memory after threshold
        prefs = await memory_manager.preferences.get_all()
        if prefs.get("memory_auto_consolidate", True):
            msgs = await memory_manager.episodic.get_recent_messages(conversation_id)
            threshold = prefs.get("memory_consolidate_after_n", 10)
            if len(msgs) >= threshold and len(msgs) % threshold == 0:
                asyncio.create_task(memory_manager.consolidate(conversation_id))
                yield {"type": "memory_stored", "data": {"status": "consolidating"}}

    async def _simple_chat(
        self, user_message: str, conversation_id: str
    ) -> AsyncGenerator[dict, None]:
        from models.ollama_client import OllamaClient
        from config import settings

        context = await memory_manager.retrieve_context(user_message, conversation_id)
        messages = memory_manager.build_messages(context, user_message)

        ollama = OllamaClient()
        if not await ollama.is_running():
            yield {"type": "token", "data": {
                "text": "⚠️ Ollama is not running. Start it with: `brew services start ollama`",
                "done": True,
            }}
            return

        # Check if active model is downloaded
        local = await ollama.list_local()
        local_names = [m["name"] for m in local]
        model_base = settings.active_model_id.split(":")[0]
        if not any(model_base in name for name in local_names):
            yield {"type": "token", "data": {
                "text": (
                    f"⚠️ No model downloaded yet.\n\n"
                    f"Go to the **Models** page and download a model first. "
                    f"Recommended: **Qwen 2.5 7B** (4.7 GB, 6 GB RAM).\n\n"
                    f"Or run in terminal: `ollama pull {settings.active_model_id}`"
                ),
                "done": True,
            }}
            return

        try:
            buffer = ""
            async for token in ollama.chat(settings.active_model_id, messages):
                buffer += token
                yield {"type": "token", "data": {"text": token, "done": False}}
            yield {"type": "token", "data": {"text": "", "done": True}}
        except Exception as e:
            log.error(f"Ollama chat error: {e}")
            yield {"type": "token", "data": {
                "text": f"⚠️ Model error: {e}. Try downloading the model again from the Models page.",
                "done": True,
            }}


orchestrator = Orchestrator()
