"""Task planner — decomposes a user request into a multi-agent TaskPlan."""
import json
import logging
import uuid
from pydantic import BaseModel

log = logging.getLogger(__name__)


class SubTask(BaseModel):
    id: str = ""
    agent_id: str
    subtask: str           # instruction for this agent
    depends_on: list[str] = []  # list of SubTask ids this must wait for

    def __init__(self, **data):
        if not data.get("id"):
            data["id"] = str(uuid.uuid4())[:8]
        super().__init__(**data)


class TaskPlan(BaseModel):
    subtasks: list[SubTask]
    rationale: str = ""


PLANNER_PROMPT = """You are a task planner for an AI assistant called Captain.
You have these specialized agents available:
{agent_list}

The user wants: "{message}"

Decompose this into subtasks for specific agents. Each subtask should be a clear, self-contained instruction.
Identify dependencies: if one subtask needs the results of another, list that dependency.

Rules:
- Use only agent_ids from the list above
- Keep subtasks focused and atomic
- If one task needs output from another, set depends_on accordingly
- Maximum 5 subtasks
- If the task is simple and only needs one agent, return just one subtask

Reply ONLY with valid JSON matching this schema exactly:
{{
  "subtasks": [
    {{"id": "t1", "agent_id": "research", "subtask": "...", "depends_on": []}},
    {{"id": "t2", "agent_id": "file", "subtask": "Use the research findings: {{t1_result}} — write them to ...", "depends_on": ["t1"]}}
  ],
  "rationale": "brief explanation of the plan"
}}"""


def _capability_fallback(intent: str, available_agents: list[str]) -> TaskPlan:
    """Single-subtask fallback when LLM planning fails."""
    intent_map = {
        "coding_task":   "coding",
        "email_task":    "email",
        "browser_task":  "browser",
        "calendar_task": "calendar",
        "file_task":     "file",
        "terminal_task": "terminal",
        "research_task": "research",
    }
    agent_id = intent_map.get(intent, "research")
    if agent_id not in available_agents and available_agents:
        agent_id = available_agents[0]
    return TaskPlan(
        subtasks=[SubTask(id="t1", agent_id=agent_id, subtask="Handle the user's request.")],
        rationale="fallback: single agent",
    )


async def plan(
    user_message: str,
    intent: str,
    available_agents: list[str],
) -> TaskPlan:
    """
    Ask the RESEARCH model to decompose the request into a TaskPlan.
    Falls back to a single-subtask plan if LLM or parsing fails.
    """
    from models.ollama_client import OllamaClient
    from models.router import model_router, ModelRole

    if not available_agents:
        return TaskPlan(subtasks=[], rationale="no agents available")

    # For single-intent tasks (not multi_agent), skip LLM decomposition
    if intent != "multi_agent":
        return _capability_fallback(intent, available_agents)

    ollama = OllamaClient()
    if not await ollama.is_running():
        return _capability_fallback(intent, available_agents)

    local = await ollama.list_local()
    if not local:
        return _capability_fallback(intent, available_agents)

    agent_lines = "\n".join(f"- {a}" for a in available_agents)
    prompt = PLANNER_PROMPT.format(
        agent_list=agent_lines,
        message=user_message[:800],
    )

    model = await model_router.get_model_for_role(ModelRole.RESEARCH)
    try:
        response = await ollama.chat_complete(
            model,
            [{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        content = response.get("message", {}).get("content", "").strip()
        # Strip markdown fences
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:].strip()
        data = json.loads(content)

        subtasks = []
        for raw in data.get("subtasks", []):
            agent_id = raw.get("agent_id", "")
            if agent_id not in available_agents:
                log.warning(f"Planner chose unknown agent '{agent_id}', skipping subtask")
                continue
            subtasks.append(SubTask(
                id=raw.get("id", str(uuid.uuid4())[:8]),
                agent_id=agent_id,
                subtask=raw.get("subtask", user_message),
                depends_on=raw.get("depends_on", []),
            ))

        if not subtasks:
            return _capability_fallback(intent, available_agents)

        return TaskPlan(
            subtasks=subtasks,
            rationale=data.get("rationale", ""),
        )
    except Exception as e:
        log.debug(f"Planner LLM failed ({e}), using fallback")
        return _capability_fallback(intent, available_agents)
