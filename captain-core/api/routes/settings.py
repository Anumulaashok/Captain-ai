import logging
from fastapi import APIRouter
from memory.preferences import preference_store

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/settings")
async def get_settings():
    return await preference_store.get_all()


@router.put("/settings")
async def update_settings(updates: dict):
    await preference_store.update_many(updates)
    return await preference_store.get_all()


@router.get("/settings/{key}")
async def get_setting(key: str):
    value = await preference_store.get(key)
    return {"key": key, "value": value}


@router.put("/settings/{key}")
async def set_setting(key: str, body: dict):
    await preference_store.set(key, body.get("value"))
    return {"key": key, "value": body.get("value")}


@router.delete("/settings/{key}")
async def delete_setting(key: str):
    await preference_store.delete(key)
    return {"ok": True}
