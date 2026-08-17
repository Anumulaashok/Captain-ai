"""Goal Agent — tracks goals, milestones, and blockers."""
import json
import logging
import time
import uuid

from agents.base import AgentBase, AgentTask, AgentResult, Tool, Permission

log = logging.getLogger(__name__)


class Agent(AgentBase):
    id = "goal"
    name = "Goal Agent"
    description = "Create and track goals, milestones, detect blockers, suggest next actions."
    capabilities = [
        "create_goal", "break_down_goal", "track_progress",
        "detect_blockers", "suggest_next_action", "generate_report",
    ]
    required_permissions = [Permission.NETWORK_FETCH]

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="create_goal",
                description="Create a new goal with title, description, and optional target date",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "target_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    },
                    "required": ["title"],
                },
                handler=self._create_goal,
            ),
            Tool(
                name="list_goals",
                description="List all active goals with progress",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=self._list_goals,
            ),
            Tool(
                name="get_goal_status",
                description="Get detailed status for a goal by ID",
                parameters={
                    "type": "object",
                    "properties": {"goal_id": {"type": "string"}},
                    "required": ["goal_id"],
                },
                handler=self._get_goal_status,
            ),
            Tool(
                name="add_blocker",
                description="Record a blocker on a goal",
                parameters={
                    "type": "object",
                    "properties": {
                        "goal_id": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["goal_id", "title"],
                },
                handler=self._add_blocker,
            ),
            Tool(
                name="break_down_goal",
                description="Break a goal into milestones and tasks using LLM",
                parameters={
                    "type": "object",
                    "properties": {
                        "goal_id": {"type": "string"},
                        "goal_description": {"type": "string"},
                    },
                    "required": ["goal_id", "goal_description"],
                },
                handler=self._break_down_goal,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()
        tools = await self.get_tools()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a goal-tracking agent. Help users define goals, "
                    "break them into milestones, track progress, and detect blockers."
                ),
            },
            {"role": "user", "content": task.user_message},
        ]
        response, tool_calls, tokens = await self._llm_tool_loop(messages, tools, task)
        return AgentResult(
            task_id=task.id,
            success=bool(response),
            response=response or "Could not process goal request.",
            tool_calls=tool_calls,
            tokens_used=tokens,
            latency_ms=int((time.time() - t_start) * 1000),
        )

    async def _create_goal(
        self, title: str, description: str = "", target_date: str | None = None
    ) -> str:
        from goals.store import goal_store
        goal = await goal_store.create_goal(title, description, target_date)
        return f"Created goal '{title}' (id: {goal['id']})"

    async def _list_goals(self) -> str:
        from goals.store import goal_store
        goals = await goal_store.list_goals()
        if not goals:
            return "No active goals."
        lines = []
        for g in goals:
            pct = int((g.get("progress") or 0) * 100)
            lines.append(f"- [{g['id'][:8]}] {g['title']}: {pct}% ({g['status']})")
        return "\n".join(lines)

    async def _get_goal_status(self, goal_id: str) -> str:
        from goals.store import goal_store
        goal = await goal_store.get_goal(goal_id)
        if not goal:
            return f"Goal {goal_id} not found."
        return json.dumps(goal, indent=2)

    async def _add_blocker(
        self, goal_id: str, title: str, description: str = ""
    ) -> str:
        from goals.store import goal_store
        result = await goal_store.add_blocker(goal_id, title, description)
        return f"Blocker added: {title}" if result else "Goal not found."

    async def _break_down_goal(self, goal_id: str, goal_description: str) -> str:
        from models.ollama_client import OllamaClient
        from models.router import model_router, ModelRole
        from goals.store import goal_store

        model = await model_router.get_model_for_role(ModelRole.PLANNER)
        ollama = OllamaClient()
        prompt = (
            f"Break this goal into 3-5 milestones, each with 2-4 tasks. "
            f"Return JSON array: [{{title, due_date, tasks: [{{title}}]}}]\n"
            f"Goal: {goal_description}"
        )
        try:
            resp = await ollama.chat_complete(model, [{"role": "user", "content": prompt}])
            content = resp.get("message", {}).get("content", "[]")
            # Extract JSON from response
            start = content.find("[")
            end = content.rfind("]") + 1
            milestones = json.loads(content[start:end]) if start >= 0 else []
            for ms in milestones:
                ms["id"] = str(uuid.uuid4())
                for t in ms.get("tasks", []):
                    t["id"] = str(uuid.uuid4())
                    t["status"] = "pending"
            await goal_store.update_goal(goal_id, milestones=milestones)
            return f"Created {len(milestones)} milestones for goal."
        except Exception as e:
            return f"Could not break down goal: {e}"
