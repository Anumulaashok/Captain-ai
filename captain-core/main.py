import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db.database import init_db
from api.websocket import event_bus, router as ws_router
from api.routes import chat, agents, models, memory, voice, settings as settings_router, accounts


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

    # Verify Pinecone connectivity
    if settings.pinecone_configured:
        from memory.semantic import SemanticMemory
        sem = SemanticMemory()
        await sem.ensure_index()
        log.info("Pinecone index ready")
    else:
        log.warning("PINECONE_API_KEY not set — semantic memory disabled")

    # Check Ollama availability
    from models.ollama_client import OllamaClient
    ollama = OllamaClient()
    if await ollama.is_running():
        log.info(f"Ollama running — active model: {settings.active_model_id}")
    else:
        log.warning("Ollama not running — start with: ollama serve")

    log.info(f"Captain AI ready on http://{settings.app_host}:{settings.app_port}")
    yield

    log.info("Captain AI shutting down...")
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
