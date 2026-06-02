import asyncio
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import json

from models.manager import model_manager

log = logging.getLogger(__name__)
router = APIRouter()


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
