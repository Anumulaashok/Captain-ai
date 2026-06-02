import asyncio
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json

from models.manager import model_manager
from models.router import model_router, ModelRole

log = logging.getLogger(__name__)
router = APIRouter()


class RoleAssignRequest(BaseModel):
    role: str
    ollama_model_id: str


@router.get("/models")
async def list_models():
    return await model_manager.list_installed()


@router.get("/models/catalog")
async def get_catalog():
    return model_manager.get_catalog()


@router.get("/models/active")
async def get_active_model():
    return {"model_id": await model_manager.get_active()}


@router.get("/models/storage")
async def get_storage():
    return await model_manager.get_storage_usage()


@router.post("/models/{model_id}/download")
async def download_model(model_id: str):
    """Start download and stream progress via SSE."""
    async def stream():
        async for progress in model_manager.download(model_id):
            yield f"data: {json.dumps(progress)}\n\n"
            # Also broadcast to all WS clients
            from api.websocket import event_bus
            await event_bus.publish("download_progress", {**progress, "model_id": model_id})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@router.post("/models/{model_id}/activate")
async def activate_model(model_id: str):
    try:
        result = await model_manager.activate(model_id)
        from api.websocket import event_bus
        await event_bus.publish("model_switched", result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/models/{model_id}")
async def delete_model(model_id: str):
    try:
        await model_manager.delete(model_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Model role routing ─────────────────────────────────────────────

@router.get("/models/roles")
async def get_role_assignments():
    """Get the current model-per-role assignments and availability."""
    return await model_router.get_all_assignments()


@router.put("/models/roles")
async def set_role_assignment(req: RoleAssignRequest):
    """Assign a specific model to a role."""
    try:
        role = ModelRole(req.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown role: {req.role}. Valid roles: {[r.value for r in ModelRole]}")
    await model_router.set_role_model(role, req.ollama_model_id)
    return {"ok": True, "role": role.value, "model": req.ollama_model_id}


@router.delete("/models/roles/{role}")
async def reset_role_assignment(role: str):
    """Reset a role back to its default model."""
    from memory.preferences import preference_store
    from models.router import DEFAULT_ROLE_MODELS
    current: dict = await preference_store.get("model_role_assignments") or {}
    current.pop(role, None)
    await preference_store.set("model_role_assignments", current)
    return {"ok": True, "role": role, "reset_to": DEFAULT_ROLE_MODELS.get(role, "")}
