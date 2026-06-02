"""Agent registry — discover, register and route to agents."""
import importlib
import logging
from typing import Type

from agents.base import AgentBase, HealthStatus

log = logging.getLogger(__name__)

# Map agent_id → module path
AGENT_MODULES = {
    "coding":   "agents.coding.agent",
    "email":    "agents.email.agent",
    "browser":  "agents.browser.agent",
    "calendar": "agents.calendar.agent",
    "file":     "agents.file.agent",
    "terminal": "agents.terminal.agent",
    "research": "agents.research.agent",
    "github":   "agents.github.agent",
    "finance":  "agents.finance.agent",
    "briefing": "agents.briefing.agent",
}


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, AgentBase] = {}
        self._loaded = False

    def _load_all(self) -> None:
        if self._loaded:
            return
        for agent_id, module_path in AGENT_MODULES.items():
            try:
                module = importlib.import_module(module_path)
                cls: Type[AgentBase] = getattr(module, "Agent")
                self._agents[agent_id] = cls()
                log.debug(f"Loaded agent: {agent_id}")
            except Exception as e:
                log.error(f"Failed to load agent {agent_id}: {e}")
        self._loaded = True

    def get(self, agent_id: str) -> AgentBase | None:
        self._load_all()
        return self._agents.get(agent_id)

    def list_all(self) -> list[AgentBase]:
        self._load_all()
        return list(self._agents.values())

    async def list_with_status(self) -> list[dict]:
        self._load_all()
        result = []
        for agent in self._agents.values():
            try:
                health = await agent.health_check()
            except Exception:
                health = HealthStatus.UNHEALTHY

            # Check DB for enabled status
            from db.database import AsyncSessionLocal
            from db.models import AgentRecord
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                rec = await db.get(AgentRecord, agent.id)

            result.append({
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "capabilities": agent.capabilities,
                "required_permissions": [p.value for p in agent.required_permissions],
                "health": health.value,
                "is_enabled": rec.is_enabled if rec else True,
            })
        return result

    def route(self, intent: str) -> list[AgentBase]:
        """Return agents matching the intent keyword."""
        self._load_all()
        keyword_map = {
            "coding_task":   ["coding"],
            "email_task":    ["email"],
            "browser_task":  ["browser"],
            "calendar_task": ["calendar"],
            "file_task":     ["file"],
            "terminal_task": ["terminal"],
            "research_task": ["research", "browser"],
            "multi_agent":   ["coding", "file", "research"],
            "briefing_task": ["briefing"],
        }
        agent_ids = keyword_map.get(intent, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def find_by_capability(self, capability: str) -> list[AgentBase]:
        """Return agents that declare a given capability string."""
        self._load_all()
        return [
            a for a in self._agents.values()
            if capability in (a.capabilities or [])
        ]


agent_registry = AgentRegistry()
