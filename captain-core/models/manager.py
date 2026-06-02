import asyncio
import logging
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.database import AsyncSessionLocal
from db.models import ModelRecord
from models.ollama_client import OllamaClient
from models.registry import KNOWN_MODELS, MODELS_BY_ID, ModelCatalogEntry

log = logging.getLogger(__name__)


class ModelManager:
    """Singleton managing model lifecycle: download, switch, delete, benchmark."""

    def __init__(self):
        self.ollama = OllamaClient()
        self._download_queues: dict[str, asyncio.Queue] = {}

    # ── Catalog ───────────────────────────────────────────────────────

    def get_catalog(self) -> list[ModelCatalogEntry]:
        return KNOWN_MODELS

    async def list_installed(self) -> list[dict]:
        """Returns catalog entries merged with install status from DB."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ModelRecord))
            db_models = {r.id: r for r in result.scalars().all()}

        ollama_local = await self.ollama.list_local()
        ollama_names = {m["name"] for m in ollama_local}

        out = []
        for entry in KNOWN_MODELS:
            db_rec = db_models.get(entry["id"])
            is_downloaded = entry["ollama_id"] in ollama_names
            out.append({
                **entry,
                "is_downloaded": is_downloaded,
                "is_active": entry["ollama_id"] == settings.active_model_id,
                "performance_tps": db_rec.performance_tps if db_rec else None,
                "last_used_at": db_rec.last_used_at.isoformat() if db_rec and db_rec.last_used_at else None,
            })
        return out

    async def get_active(self) -> str:
        return settings.active_model_id

    # ── Download ──────────────────────────────────────────────────────

    async def download(self, model_id: str) -> AsyncGenerator[dict, None]:
        """Stream download progress dicts: {pct, speed_mb, status}."""
        entry = MODELS_BY_ID.get(model_id)
        if not entry:
            raise ValueError(f"Unknown model: {model_id}")

        ollama_id = entry["ollama_id"]
        log.info(f"Starting download: {ollama_id}")

        total_bytes = int(entry["size_gb"] * 1024 ** 3)
        last_completed = 0

        async for chunk in self.ollama.pull(ollama_id):
            completed = chunk.get("completed", 0)
            total = chunk.get("total", total_bytes) or total_bytes
            pct = round((completed / total) * 100, 1) if total else 0
            speed_mb = round((completed - last_completed) / 1024 ** 2, 2)
            last_completed = completed
            yield {"pct": pct, "speed_mb": speed_mb, "status": chunk.get("status", "downloading")}

        # Record in DB
        await self._upsert_model_record(entry, is_downloaded=True)
        log.info(f"Download complete: {model_id}")
        yield {"pct": 100.0, "speed_mb": 0, "status": "complete", "model_id": model_id}

    async def _upsert_model_record(self, entry: ModelCatalogEntry, **kwargs) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ModelRecord).where(ModelRecord.id == entry["id"])
            )
            rec = result.scalar_one_or_none()
            if rec:
                for k, v in kwargs.items():
                    setattr(rec, k, v)
                if "is_downloaded" in kwargs and kwargs["is_downloaded"]:
                    rec.downloaded_at = datetime.utcnow()
            else:
                rec = ModelRecord(
                    id=entry["id"],
                    name=entry["name"],
                    provider=entry["provider"],
                    family=entry["family"],
                    size_gb=entry["size_gb"],
                    ram_required_gb=entry["ram_required_gb"],
                    quantization=entry["quantization"],
                    downloaded_at=datetime.utcnow() if kwargs.get("is_downloaded") else None,
                    **kwargs,
                )
                db.add(rec)
            await db.commit()

    # ── Activate ──────────────────────────────────────────────────────

    async def activate(self, model_id: str) -> dict:
        """Switch active model (zero-downtime: load new → swap → unload old)."""
        entry = MODELS_BY_ID.get(model_id)
        if not entry:
            raise ValueError(f"Unknown model: {model_id}")

        old_model = settings.active_model_id
        new_model = entry["ollama_id"]

        # Ensure new model is available
        if not await self.ollama.ensure_model_loaded(new_model):
            raise RuntimeError(f"Could not load model {new_model}")

        # Swap active pointer (in-memory + persisted)
        settings.active_model_id = new_model
        from memory.preferences import preference_store
        await preference_store.set("active_model", new_model)
        log.info(f"Active model switched: {old_model} → {new_model}")

        # Update DB
        async with AsyncSessionLocal() as db:
            await db.execute(update(ModelRecord).values(is_active=False))
            result = await db.execute(select(ModelRecord).where(ModelRecord.id == model_id))
            rec = result.scalar_one_or_none()
            if rec:
                rec.is_active = True
                rec.last_used_at = datetime.utcnow()
            await db.commit()

        # Benchmark in background
        asyncio.create_task(self._background_benchmark(model_id, new_model))
        return {"model_id": model_id, "ollama_id": new_model}

    async def _background_benchmark(self, model_id: str, ollama_id: str) -> None:
        try:
            tps = await self.ollama.benchmark(ollama_id)
            log.info(f"Benchmark {model_id}: {tps} tokens/sec")
            await self._upsert_model_record(MODELS_BY_ID[model_id], performance_tps=tps)
        except Exception as e:
            log.warning(f"Benchmark failed for {model_id}: {e}")

    # ── Delete ────────────────────────────────────────────────────────

    async def delete(self, model_id: str) -> None:
        entry = MODELS_BY_ID.get(model_id)
        if not entry:
            raise ValueError(f"Unknown model: {model_id}")
        if entry["ollama_id"] == settings.active_model_id:
            raise ValueError("Cannot delete the currently active model")

        await self.ollama.delete(entry["ollama_id"])
        await self._upsert_model_record(entry, is_downloaded=False, is_active=False)
        log.info(f"Deleted model: {model_id}")

    # ── Storage ───────────────────────────────────────────────────────

    async def get_storage_usage(self) -> dict:
        local = await self.ollama.list_local()
        total_bytes = sum(m.get("size", 0) for m in local)
        return {
            "installed_count": len(local),
            "total_gb": round(total_bytes / 1024 ** 3, 2),
            "models": [{"name": m["name"], "size_gb": round(m.get("size", 0) / 1024 ** 3, 2)} for m in local],
        }


model_manager = ModelManager()
