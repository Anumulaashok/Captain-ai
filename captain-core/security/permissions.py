"""Agent permission management — request, grant, deny, persist."""
import asyncio
import logging
from agents.base import Permission

log = logging.getLogger(__name__)


class PermissionManager:

    async def has_permission(self, agent_id: str, permission: Permission) -> bool:
        from memory.preferences import preference_store
        all_prefs = await preference_store.get_all()
        agent_perms: dict = all_prefs.get("agent_permissions", {})
        agent_grants: list = agent_perms.get(agent_id, [])
        return permission.value in agent_grants

    async def grant(self, agent_id: str, permission: Permission) -> None:
        from memory.preferences import preference_store
        all_prefs = await preference_store.get_all()
        agent_perms: dict = all_prefs.get("agent_permissions", {})
        grants = set(agent_perms.get(agent_id, []))
        grants.add(permission.value)
        agent_perms[agent_id] = list(grants)
        await preference_store.set("agent_permissions", agent_perms)
        log.info(f"Granted {permission.value} to {agent_id}")

    async def revoke(self, agent_id: str, permission: Permission) -> None:
        from memory.preferences import preference_store
        all_prefs = await preference_store.get_all()
        agent_perms: dict = all_prefs.get("agent_permissions", {})
        grants = set(agent_perms.get(agent_id, []))
        grants.discard(permission.value)
        agent_perms[agent_id] = list(grants)
        await preference_store.set("agent_permissions", agent_perms)

    async def grant_all(self, agent_id: str, permissions: list[Permission]) -> None:
        for p in permissions:
            await self.grant(agent_id, p)

    async def get_agent_permissions(self, agent_id: str) -> list[str]:
        from memory.preferences import preference_store
        all_prefs = await preference_store.get_all()
        return all_prefs.get("agent_permissions", {}).get(agent_id, [])


permission_manager = PermissionManager()
