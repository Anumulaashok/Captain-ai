import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from memory.manager import memory_manager
from memory.semantic import semantic_memory

log = logging.getLogger(__name__)
router = APIRouter()


class MemoryCreateRequest(BaseModel):
    type: str = "fact"
    key: str | None = None
    value: str
    source: str | None = None


@router.get("/memory")
async def search_memory(q: str = Query("", description="Search query"), k: int = 10):
    if not q:
        # Return recent entries from DB
        from db.database import AsyncSessionLocal
        from db.models import MemoryEntry
        from sqlalchemy import select, desc
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MemoryEntry).order_by(desc(MemoryEntry.created_at)).limit(k)
            )
            entries = result.scalars().all()
        return [
            {
                "id": e.id,
                "type": e.type,
                "key": e.key,
                "value": e.value,
                "source": e.source,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ]

    result = await semantic_memory.search(q, k=k)
    return [
        {
            "id": m.id,
            "type": m.type,
            "key": m.key,
            "value": m.value,
            "source": m.source,
            "score": score,
        }
        for m, score in zip(result.memories, result.scores)
    ]


@router.post("/memory")
async def create_memory(req: MemoryCreateRequest):
    entry_id = await memory_manager.store_memory(
        type=req.type, value=req.value, key=req.key, source=req.source
    )
    return {"id": entry_id}


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str):
    from db.database import AsyncSessionLocal
    from db.models import MemoryEntry
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(MemoryEntry).where(MemoryEntry.id == memory_id))
        entry = result.scalar_one_or_none()
        if not entry:
            raise HTTPException(status_code=404, detail="Memory not found")
        if entry.pinecone_id:
            await semantic_memory.delete(entry.pinecone_id)
        await db.delete(entry)
        await db.commit()
    return {"ok": True}


@router.get("/memory/stats")
async def get_memory_stats():
    pinecone_stats = await semantic_memory.get_stats()
    from db.database import AsyncSessionLocal
    from db.models import MemoryEntry
    from sqlalchemy import func, select
    async with AsyncSessionLocal() as db:
        count_result = await db.execute(select(func.count()).select_from(MemoryEntry))
        total_entries = count_result.scalar()
    return {
        "total_entries": total_entries,
        "pinecone": pinecone_stats,
    }
