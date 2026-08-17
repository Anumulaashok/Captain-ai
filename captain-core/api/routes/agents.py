import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agents.registry import agent_registry
from agents.base import AgentTask

log = logging.getLogger(__name__)
router = APIRouter()


class AgentRunRequest(BaseModel):
    message: str
    context: dict = {}


class PermissionUpdateRequest(BaseModel):
    permissions: list[str]


@router.get("/agents")
async def list_agents():
    return await agent_registry.list_with_status()


@router.post("/agents/{agent_id}/enable")
async def enable_agent(agent_id: str):
    from db.database import AsyncSessionLocal
    from db.models import AgentRecord
    async with AsyncSessionLocal() as db:
        rec = await db.get(AgentRecord, agent_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Agent not found")
        rec.is_enabled = True
        await db.commit()
    return {"ok": True, "agent_id": agent_id}


@router.post("/agents/{agent_id}/disable")
async def disable_agent(agent_id: str):
    from db.database import AsyncSessionLocal
    from db.models import AgentRecord
    async with AsyncSessionLocal() as db:
        rec = await db.get(AgentRecord, agent_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Agent not found")
        rec.is_enabled = False
        await db.commit()
    return {"ok": True, "agent_id": agent_id}


@router.post("/agents/{agent_id}/run")
async def run_agent(agent_id: str, req: AgentRunRequest):
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    task = AgentTask(
        agent_id=agent_id,
        intent=f"{agent_id}_task",
        user_message=req.message,
        context=req.context,
    )
    result = await agent.run(task)
    return result.dict()


@router.post("/agents/{agent_id}/permissions")
async def update_permissions(agent_id: str, req: PermissionUpdateRequest):
    from security.permissions import permission_manager
    from agents.base import Permission
    for perm_str in req.permissions:
        try:
            perm = Permission(perm_str)
            await permission_manager.grant(agent_id, perm)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid permission: {perm_str}")
    return {"ok": True}


@router.get("/agents/{agent_id}/permissions")
async def get_permissions(agent_id: str):
    from security.permissions import permission_manager
    return {"permissions": await permission_manager.get_agent_permissions(agent_id)}


class ApprovalRequest(BaseModel):
    approved: bool
    agent_id: str = ""      # sent by frontend so grant works even if Future is gone
    permission: str = ""    # same


@router.post("/agents/approvals/{request_id}")
async def resolve_approval(request_id: str, req: ApprovalRequest):
    """Called by the UI Approve/Deny modal to resume a paused agent.

    Always returns 200 — even if the Future is gone (e.g. server reloaded while
    the modal was open).  When approved, also grants the permission directly so
    the agent won't be blocked again.
    """
    from security.approvals import approval_manager
    from security.permissions import permission_manager
    from agents.base import Permission

    # Unblock the waiting Future (may already be gone — that's OK)
    approval_manager.resolve(request_id, req.approved)

    # Grant / record the permission directly so it persists regardless
    if req.approved and req.agent_id and req.permission:
        try:
            await permission_manager.grant(req.agent_id, Permission(req.permission))
        except ValueError:
            pass  # unknown permission string — ignore

    return {"ok": True, "approved": req.approved}


@router.get("/agents/approvals/pending")
async def list_pending_approvals():
    """Returns request_ids currently awaiting user action."""
    from security.approvals import approval_manager
    return {"pending": approval_manager.list_pending()}
