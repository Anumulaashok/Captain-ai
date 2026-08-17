import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db.database import init_db
from api.websocket import event_bus, router as ws_router
from api.routes import (
    chat, agents, models, memory, voice,
    settings as settings_router, accounts, integrations, goals,
)


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("captain")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Captain AI starting up...")
    settings.ensure_dirs()

    # Init PostgreSQL schema
    await init_db()
    log.info("Database ready (Neon PostgreSQL)")

    # Seed default agents into DB if first run
    from db.seed import seed_defaults
    await seed_defaults()

    # Pre-grant safe read-only permissions so agents don't ask for them every run.
    # Sensitive write/execute permissions (email:write, terminal:execute) still require
    # user approval each session.
    from security.permissions import permission_manager
    from agents.base import Permission
    safe_grants = {
        "browser":  [Permission.NETWORK_FETCH, Permission.BROWSER_OPEN],
        "research": [Permission.NETWORK_FETCH, Permission.BROWSER_OPEN],
        "gmail":    [Permission.NETWORK_FETCH],
        "github":   [Permission.NETWORK_FETCH],
        "file":     [Permission.FILESYSTEM_READ],
        "briefing": [Permission.NETWORK_FETCH],
    }
    for agent_id, perms in safe_grants.items():
        for perm in perms:
            if not await permission_manager.has_permission(agent_id, perm):
                await permission_manager.grant(agent_id, perm)
    log.info("Safe permissions pre-granted")

    # Verify Pinecone connectivity
    if settings.pinecone_configured:
        from memory.semantic import SemanticMemory
        sem = SemanticMemory()
        await sem.ensure_index()
        log.info("Pinecone index ready")
    else:
        log.warning("PINECONE_API_KEY not set — semantic memory disabled")

    # Resolve active model: saved preference → env default → first available
    from memory.preferences import preference_store
    from models.ollama_client import OllamaClient
    ollama = OllamaClient()

    if await ollama.is_running():
        local = await ollama.list_local()
        local_names = [m["name"] for m in local]
        log.info(f"Ollama local models: {local_names}")

        # 1. Try saved preference (only trust if it's actually downloaded)
        saved = await preference_store.get("active_model")
        if saved and any(saved.split(":")[0] in n for n in local_names):
            settings.active_model_id = saved
        # 2. Try env/config default
        elif any(settings.active_model_id.split(":")[0] in n for n in local_names):
            pass  # keep settings.active_model_id as-is
        # 3. Auto-pick first available model
        elif local_names:
            settings.active_model_id = local_names[0]
            await preference_store.set("active_model", settings.active_model_id)
            log.info(f"Auto-selected available model: {settings.active_model_id}")
        else:
            log.warning("No models downloaded. Visit the Models page to download one.")

        log.info(f"Ollama running — active model: {settings.active_model_id}")
    else:
        log.warning("Ollama not running — start with: brew services start ollama")

    # Start background agent scheduler
    from scheduler.service import start_scheduler
    start_scheduler()

    # Start background watchers
    try:
        from watchers.scheduler import watcher_scheduler
        watcher_scheduler.start()
        log.info("Background watchers started")
    except Exception as e:
        log.warning(f"Watchers not started: {e}")

    # Start briefing scheduler (morning / EOD)
    try:
        from briefing.scheduler import briefing_scheduler
        briefing_scheduler.start()
        log.info("Briefing scheduler started")
    except Exception as e:
        log.warning(f"Briefing scheduler not started: {e}")

    log.info(f"Captain AI ready on http://{settings.app_host}:{settings.app_port}")
    yield

    log.info("Captain AI shutting down...")
    try:
        from watchers.scheduler import watcher_scheduler
        watcher_scheduler.stop()
    except Exception:
        pass
    try:
        from briefing.scheduler import briefing_scheduler
        briefing_scheduler.stop()
    except Exception:
        pass
    # Stop background scheduler
    try:
        from scheduler.service import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    # Stop voice engine if running
    try:
        from voice.engine import voice_engine
        await voice_engine.stop()
    except Exception:
        pass


app = FastAPI(
    title="Captain AI",
    version="1.0.0",
    description="Local macOS AI assistant backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "tauri://localhost",
        "http://localhost:1420",   # Tauri dev server
        "http://127.0.0.1:1420",
        "http://localhost:8765",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers
app.include_router(chat.router,     prefix="/api", tags=["chat"])
app.include_router(agents.router,   prefix="/api", tags=["agents"])
app.include_router(models.router,   prefix="/api", tags=["models"])
app.include_router(memory.router,   prefix="/api", tags=["memory"])
app.include_router(voice.router,    prefix="/api", tags=["voice"])
app.include_router(settings_router.router, prefix="/api", tags=["settings"])
app.include_router(accounts.router, prefix="/api", tags=["accounts"])
app.include_router(integrations.router, prefix="/api", tags=["integrations"])
app.include_router(goals.router, prefix="/api", tags=["goals"])

# WebSocket endpoint
app.include_router(ws_router, tags=["ws"])


@app.get("/health")
async def health():
    from models.ollama_client import OllamaClient
    ollama_ok = await OllamaClient().is_running()
    return {
        "status": "ok",
        "ollama": ollama_ok,
        "pinecone": settings.pinecone_configured,
        "active_model": settings.active_model_id,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
