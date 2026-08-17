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
    "gmail":    "agents.gmail.agent",
    "browser":  "agents.browser.agent",
    "calendar": "agents.calendar.agent",
    "file":     "agents.file.agent",
    "terminal": "agents.terminal.agent",
    "research": "agents.research.agent",
    "github":   "agents.github.agent",
    "finance":  "agents.finance.agent",
    "briefing": "agents.briefing.agent",
    "builder":  "agents.builder.agent",
    "goal":     "agents.goal.agent",
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
            "email_task":    ["gmail", "email"],   # gmail first (IMAP, always works); email = Apple Mail fallback
            "browser_task":  ["browser"],
            "calendar_task": ["calendar"],
            "file_task":     ["file"],
            "terminal_task": ["terminal"],
            "research_task": ["research", "browser"],
            "multi_agent":   ["coding", "file", "research"],
            "briefing_task": ["briefing"],
            "goal_task":     ["goal"],
        }
        agent_ids = keyword_map.get(intent, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def has_agent(self, agent_id: str) -> bool:
        self._load_all()
        return agent_id in self._agents

    def register_dynamic(self, agent_id: str) -> bool:
        """Hot-load an agent module at runtime."""
        if agent_id in self._agents:
            return True
        module_path = f"agents.{agent_id}.agent"
        try:
            import importlib
            module = importlib.import_module(module_path)
            cls: Type[AgentBase] = getattr(module, "Agent")
            self._agents[agent_id] = cls()
            AGENT_MODULES[agent_id] = module_path
            log.info(f"Dynamically registered agent: {agent_id}")
            return True
        except Exception as e:
            log.error(f"Dynamic registration failed for {agent_id}: {e}")
            return False

    def reload_agent(self, agent_id: str) -> bool:
        """Reload an agent module after code changes."""
        import importlib
        module_path = AGENT_MODULES.get(agent_id)
        if not module_path:
            return False
        try:
            if module_path in importlib.sys.modules:
                module = importlib.reload(importlib.sys.modules[module_path])
            else:
                module = importlib.import_module(module_path)
            cls: Type[AgentBase] = getattr(module, "Agent")
            self._agents[agent_id] = cls()
            log.info(f"Reloaded agent: {agent_id}")
            return True
        except Exception as e:
            log.error(f"Reload failed for {agent_id}: {e}")
            return False

    def find_by_capability(self, capability: str) -> list[AgentBase]:
        """Return agents that declare a given capability string."""
        self._load_all()
        return [
            a for a in self._agents.values()
            if capability in (a.capabilities or [])
        ]


agent_registry = AgentRegistry()
