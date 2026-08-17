"""
Task executor — runs a TaskPlan across multiple agents in parallel waves,
respecting depends_on ordering. Persists each run as a TaskRecord.
"""
import asyncio
import logging
import time
from datetime import datetime

from orchestrator.planner import TaskPlan, SubTask
from agents.base import AgentTask, AgentResult

log = logging.getLogger(__name__)


async def _persist_task(
    subtask: SubTask,
    conversation_id: str,
    parent_task_id: str | None,
    status: str,
    result: AgentResult | None = None,
    error: str | None = None,
    started_at: datetime | None = None,
) -> None:
    """Write / update a TaskRecord in the DB."""
    try:
        from db.database import AsyncSessionLocal
        from db.models import TaskRecord
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            rec = await db.get(TaskRecord, subtask.id)
            if rec is None:
                rec = TaskRecord(
                    id=subtask.id,
                    conversation_id=conversation_id,
                    agent_id=subtask.agent_id,
                    parent_task_id=parent_task_id,
                    status=status,
                    intent=subtask.agent_id,
                    input={"subtask": subtask.subtask},
                    started_at=started_at,
                    created_at=datetime.utcnow(),
                )
                db.add(rec)
            else:
                rec.status = status
                if result:
                    rec.output = {
                        "response": result.response[:2000],
                        "tool_calls": len(result.tool_calls),
                        "artifacts": len(result.artifacts),
                    }
                if error:
                    rec.error = error
                if status in ("success", "failed"):
                    rec.completed_at = datetime.utcnow()
            await db.commit()
    except Exception as e:
        log.debug(f"TaskRecord persist failed (non-fatal): {e}")


async def _run_subtask(
    subtask: SubTask,
    conversation_id: str,
    parent_task_id: str | None,
    upstream_results: dict[str, AgentResult],
) -> AgentResult:
    """Execute a single subtask, injecting upstream results into context."""
    from agents.registry import agent_registry

    agent = agent_registry.get(subtask.agent_id)
    if agent is None:
        log.error(f"Agent '{subtask.agent_id}' not found")
        return AgentResult(
            task_id=subtask.id,
            success=False,
            response=f"Agent '{subtask.agent_id}' is not available.",
            error="agent_not_found",
        )

    # Build the subtask message, injecting any upstream results as context
    user_message = subtask.subtask
    # Mark as multi-agent context so _make_delegate_tool activates if needed
    context: dict = {"source": "multi_agent"}
    if upstream_results:
        context_parts = []
        for dep_id, dep_result in upstream_results.items():
            if dep_result.success:
                context_parts.append(
                    f"[Results from subtask {dep_id}]:\n{dep_result.response[:1000]}"
                )
        if context_parts:
            user_message = user_message + "\n\n" + "\n\n".join(context_parts)

    task = AgentTask(
        id=subtask.id,
        agent_id=subtask.agent_id,
        intent=f"{subtask.agent_id}_task",
        user_message=user_message,
        context=context,
    )

    started_at = datetime.utcnow()
    await _persist_task(subtask, conversation_id, parent_task_id, "running", started_at=started_at)

    try:
        result = await agent.run(task)
        await _persist_task(subtask, conversation_id, parent_task_id, "success", result=result)
        return result
    except Exception as e:
        log.error(f"Subtask {subtask.id} ({subtask.agent_id}) failed: {e}")
        err_result = AgentResult(
            task_id=subtask.id,
            success=False,
            response=f"The {subtask.agent_id} agent encountered an error: {e}",
            error=str(e),
        )
        await _persist_task(subtask, conversation_id, parent_task_id, "failed", error=str(e))
        return err_result


async def execute(
    plan: TaskPlan,
    conversation_id: str,
    parent_task_id: str | None = None,
    on_subtask_start=None,   # async callback(subtask)
    on_subtask_done=None,    # async callback(subtask, result)
) -> list[AgentResult]:
    """
    Execute a TaskPlan in dependency-order waves.

    - Subtasks with no depends_on run in parallel (wave 0).
    - Subtasks whose deps are all done run in the next wave, with upstream results injected.
    - Returns results in subtask order.
    """
    if not plan.subtasks:
        return []

    results: dict[str, AgentResult] = {}      # subtask.id → AgentResult
    pending = {st.id: st for st in plan.subtasks}
    ordered_results: list[AgentResult] = []

    max_waves = len(plan.subtasks) + 1        # guard against circular deps
    waves = 0

    while pending and waves < max_waves:
        waves += 1
        # Find subtasks whose all dependencies are satisfied
        ready = [
            st for st in pending.values()
            if all(dep in results for dep in st.depends_on)
        ]

        if not ready:
            log.warning("Executor: no ready subtasks — possible circular dependency, stopping")
            break

        # Notify start for all ready subtasks
        if on_subtask_start:
            for st in ready:
                try:
                    await on_subtask_start(st)
                except Exception:
                    pass

        # Run ready subtasks in parallel
        upstream_maps = [
            {dep: results[dep] for dep in st.depends_on if dep in results}
            for st in ready
        ]
        wave_results = await asyncio.gather(
            *[
                _run_subtask(st, conversation_id, parent_task_id, upstream)
                for st, upstream in zip(ready, upstream_maps)
            ]
        )

        for st, result in zip(ready, wave_results):
            results[st.id] = result
            del pending[st.id]
            if on_subtask_done:
                try:
                    await on_subtask_done(st, result)
                except Exception:
                    pass

    # Return in original plan order
    return [results[st.id] for st in plan.subtasks if st.id in results]


async def aggregate(
    results: list[AgentResult],
    original_message: str,
) -> str:
    """
    Ask the CHAT model to synthesize multiple agent results into one response.
    Falls back to concatenation if LLM is unavailable.
    """
    if not results:
        return "No results from agents."

    if len(results) == 1:
        return results[0].response

    # Build a summary of all results for the LLM to synthesize
    parts = []
    for i, r in enumerate(results, 1):
        status = "completed" if r.success else "failed"
        snippet = r.response[:600] if r.response else "(no output)"
        parts.append(f"Agent {i} ({status}):\n{snippet}")

    combined = "\n\n---\n\n".join(parts)
    synthesis_prompt = (
        f"The user asked: \"{original_message}\"\n\n"
        f"Multiple agents worked on this. Here are their results:\n\n{combined}\n\n"
        "Write a single, coherent response to the user that integrates all the above. "
        "Be concise. Don't say 'Agent 1 said...' — just give the answer."
    )

    from models.gemini_client import gemini_client
    from models.ollama_client import OllamaClient
    from models.router import model_router, ModelRole
    from config import settings

    synth_messages = [{"role": "user", "content": synthesis_prompt}]

    # Prefer Gemini for synthesis (better quality, no tool-schema issues)
    if await gemini_client.is_configured():
        try:
            text = ""
            async for token in gemini_client.chat(settings.gemini_model, synth_messages, temperature=0.3, max_tokens=600):
                text += token
            return text.strip() or combined
        except Exception as e:
            log.debug(f"Gemini aggregation failed ({e}), trying Ollama")

    ollama = OllamaClient()
    if not await ollama.is_running():
        return "\n\n".join(r.response for r in results if r.response)

    model = await model_router.get_model_for_role(ModelRole.CHAT)
    try:
        text = ""
        async for token in ollama.chat(model, synth_messages, temperature=0.3, max_tokens=600):
            text += token
        return text.strip() or combined
    except Exception as e:
        log.debug(f"Aggregation LLM failed ({e}), using concatenation")
        return "\n\n".join(r.response for r in results if r.response)
