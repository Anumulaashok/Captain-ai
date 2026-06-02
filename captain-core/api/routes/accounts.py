"""
Accounts API — surfaces connection status for all integrated services.
This powers the "Accounts" panel that opens when you click the app icon.

Services tracked:
  - Neon PostgreSQL   (always-on — our primary DB)
  - Pinecone          (vector memory)
  - Ollama            (local LLM runtime)
  - OpenAI            (future cloud plugin)
  - Anthropic         (future cloud plugin)
  - Google Gemini     (future cloud plugin)
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import settings
from security.keychain import keychain

log = logging.getLogger(__name__)
router = APIRouter()


class CloudKeyRequest(BaseModel):
    service: str   # openai | anthropic | gemini
    api_key: str


# ── Status helpers ────────────────────────────────────────────────────


async def _check_neon() -> dict:
    try:
        from db.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.fetchone()
        return {"status": "connected", "provider": "Neon", "type": "postgresql"}
    except Exception as e:
        return {"status": "error", "error": str(e), "provider": "Neon", "type": "postgresql"}


async def _check_pinecone() -> dict:
    if not settings.pinecone_configured:
        return {"status": "not_configured", "provider": "Pinecone", "type": "vector_db"}
    try:
        from memory.semantic import semantic_memory
        stats = await semantic_memory.get_stats()
        return {
            "status": "connected",
            "provider": "Pinecone",
            "type": "vector_db",
            "index": settings.pinecone_index_name,
            "vectors": stats.get("total_vectors", 0),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "provider": "Pinecone", "type": "vector_db"}


async def _check_ollama() -> dict:
    try:
        from models.ollama_client import OllamaClient
        client = OllamaClient()
        is_up = await client.is_running()
        if is_up:
            local = await client.list_local()
            return {
                "status": "running",
                "provider": "Ollama",
                "type": "llm_runtime",
                "active_model": settings.active_model_id,
                "installed_models": len(local),
            }
        return {"status": "stopped", "provider": "Ollama", "type": "llm_runtime"}
    except Exception as e:
        return {"status": "error", "error": str(e), "provider": "Ollama", "type": "llm_runtime"}


def _check_cloud_key(service: str) -> dict:
    """Check if a cloud API key is stored in Keychain or env."""
    key_map = {
        "openai":    settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "gemini":    settings.gemini_api_key,
    }
    labels = {
        "openai":    {"provider": "OpenAI",         "type": "cloud_llm"},
        "anthropic": {"provider": "Anthropic",      "type": "cloud_llm"},
        "gemini":    {"provider": "Google Gemini",  "type": "cloud_llm"},
    }
    env_key = key_map.get(service, "")
    # Also check Keychain
    keychain_key = keychain.retrieve(f"{service}_api_key") or ""
    has_key = bool(env_key or keychain_key)
    return {
        **labels.get(service, {}),
        "status": "configured" if has_key else "not_configured",
        "source": "keychain" if keychain_key else ("env" if env_key else None),
    }


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/accounts")
async def get_accounts():
    """Return status of all connected services — used by app icon Account panel."""
    import asyncio
    neon, pinecone, ollama = await asyncio.gather(
        _check_neon(),
        _check_pinecone(),
        _check_ollama(),
    )
    cloud = [_check_cloud_key(s) for s in ("openai", "anthropic", "gemini")]
    return {
        "local": [neon, pinecone, ollama],
        "cloud": cloud,
    }


@router.get("/accounts/neon")
async def neon_status():
    return await _check_neon()


@router.get("/accounts/pinecone")
async def pinecone_status():
    return await _check_pinecone()


@router.get("/accounts/ollama")
async def ollama_status():
    return await _check_ollama()


@router.post("/accounts/cloud-key")
async def add_cloud_key(req: CloudKeyRequest):
    """
    Store a cloud API key in macOS Keychain.
    Called from the Accounts panel when user connects a cloud provider.
    """
    valid_services = {"openai", "anthropic", "gemini"}
    if req.service not in valid_services:
        raise HTTPException(status_code=400, detail=f"Unknown service: {req.service}")
    if not req.api_key.strip():
        raise HTTPException(status_code=400, detail="API key cannot be empty")

    keychain_key = f"{req.service}_api_key"
    keychain.store(keychain_key, req.api_key.strip())
    log.info(f"Stored {req.service} API key in Keychain")

    return {
        "ok": True,
        "service": req.service,
        "stored_in": "keychain",
        "message": f"{req.service.title()} API key saved to macOS Keychain",
    }


@router.delete("/accounts/cloud-key/{service}")
async def remove_cloud_key(service: str):
    """Remove a cloud API key from Keychain."""
    keychain.delete(f"{service}_api_key")
    log.info(f"Removed {service} API key from Keychain")
    return {"ok": True, "service": service}


@router.get("/accounts/cloud-key/{service}")
async def check_cloud_key(service: str):
    return _check_cloud_key(service)
