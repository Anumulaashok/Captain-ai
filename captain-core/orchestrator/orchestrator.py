"""Central Orchestrator — routes messages to the right model and agent(s)."""
import asyncio
import logging
import time
import uuid
from collections.abc import AsyncGenerator

from orchestrator.intent import classify_intent
from orchestrator.planner import plan
from orchestrator.executor import execute, aggregate
from memory.manager import memory_manager
from agents.registry import agent_registry
from agents.base import AgentTask
from models.router import model_router, ModelRole, INTENT_TO_ROLE
from api.websocket import event_bus

log = logging.getLogger(__name__)

# Intents that should always try multiple agents
MULTI_AGENT_INTENTS = {"multi_agent", "research_task"}


class Orchestrator:

    async def process(
        self,
        user_message: str,
        conversation_id: str,
    ) -> AsyncGenerator[dict, None]:
        """
        Main entry point. Yields SSE event dicts:
          {"type": "token",            "data": {"text": str, "done": bool}}
          {"type": "model_used",       "data": {"role": str, "model": str}}
          {"type": "plan_created",     "data": {"subtasks": [...], "rationale": str}}
          {"type": "agent_started",    "data": {"agent_id": str, "agent_name": str, "subtask_id": str}}
          {"type": "agent_finished",   "data": {...}}
          {"type": "memory_stored",    "data": {...}}
        """
        t_start = time.time()
        parent_task_id = str(uuid.uuid4())

        await memory_manager.episodic.add_message(conversation_id, "user", user_message)

        # Classify intent using the FAST model
        intent = await classify_intent(user_message)
        log.info(f"Intent: {intent.intent} ({intent.confidence:.2f})")

        full_response = ""

        if intent.intent == "simple_chat" or intent.confidence < 0.6:
            # ── Simple chat: stream directly from LLM ──────────────────────
            async for event in self._llm_chat(user_message, conversation_id, intent.intent):
                if event["type"] == "token":
                    full_response += event["data"].get("text", "")
                yield event

        else:
            # ── Agent path: plan → execute ─────────────────────────────────
            all_agents = agent_registry.list_all()
            enabled_agents = await self._filter_enabled(all_agents)
            available_ids = [a.id for a in enabled_agents]

            # If the naturally-routed agents for this intent are all disabled,
            # fall back to a plain LLM chat rather than picking an unrelated agent.
            routed = agent_registry.route(intent.intent)
            routed_enabled = [a for a in routed if a.id in available_ids]
            if routed and not routed_enabled and intent.intent != "multi_agent":
                log.info(f"Agents for '{intent.intent}' are all disabled — falling back to LLM chat")
                async for event in self._llm_chat(user_message, conversation_id, intent.intent):
                    if event["type"] == "token":
                        full_response += event["data"].get("text", "")
                    yield event
                # skip to memory consolidation at the end
            elif not enabled_agents:
                async for event in self._llm_chat(user_message, conversation_id, intent.intent):
                    if event["type"] == "token":
                        full_response += event["data"].get("text", "")
                    yield event
            else:
                # Build task plan (single subtask for focused intents, multi for multi_agent)
                task_plan = await plan(user_message, intent.intent, available_ids)

                yield {
                    "type": "plan_created",
                    "data": {
                        "parent_task_id": parent_task_id,
                        "subtasks": [st.model_dump() for st in task_plan.subtasks],
                        "rationale": task_plan.rationale,
                    },
                }
                await event_bus.publish("plan_created", {
                    "parent_task_id": parent_task_id,
                    "subtask_count": len(task_plan.subtasks),
                    "agents": [st.agent_id for st in task_plan.subtasks],
                })

                # ── Execution callbacks that stream events ──
                async def on_start(subtask):
                    agent = agent_registry.get(subtask.agent_id)
                    name = agent.name if agent else subtask.agent_id
                    event = {
                        "type": "agent_started",
                        "data": {
                            "agent_id": subtask.agent_id,
                            "agent_name": name,
                            "subtask_id": subtask.id,
                            "subtask": subtask.subtask[:120],
                        },
                    }
                    await event_bus.publish("agent_started", event["data"])

                async def on_done(subtask, result):
                    event_data = {
                        "agent_id": subtask.agent_id,
                        "subtask_id": subtask.id,
                        "success": result.success,
                        "tool_calls": len(result.tool_calls),
                        "artifacts": [a.model_dump() for a in result.artifacts],
                        "latency_ms": result.latency_ms,
                    }
                    await event_bus.publish("agent_finished", event_data)

                # ── Run the plan ──
                results = await execute(
                    task_plan,
                    conversation_id,
                    parent_task_id=parent_task_id,
                    on_subtask_start=on_start,
                    on_subtask_done=on_done,
                )

                # Stream a final synthetic agent_finished for the whole plan
                all_artifacts = [a for r in results for a in r.artifacts]
                yield {
                    "type": "agent_finished",
                    "data": {
                        "parent_task_id": parent_task_id,
                        "subtask_count": len(results),
                        "success": any(r.success for r in results),
                        "artifacts": [a.model_dump() for a in all_artifacts],
                    },
                }

                # Aggregate and stream as tokens
                full_response = await aggregate(results, user_message)
                words = full_response.split(" ")
                for i, word in enumerate(words):
                    done = i == len(words) - 1
                    yield {"type": "token", "data": {"text": word + ("" if done else " "), "done": done}}
                    await asyncio.sleep(0)

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

        role = INTENT_TO_ROLE.get(intent, ModelRole.CHAT)
        model = await model_router.get_model_for_role(role)

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
            try:
                async with AsyncSessionLocal() as db:
                    rec = await db.get(AgentRecord, agent.id)
                if rec is None or rec.is_enabled:
                    enabled.append(agent)
            except Exception:
                enabled.append(agent)
        return enabled


orchestrator = Orchestrator()
