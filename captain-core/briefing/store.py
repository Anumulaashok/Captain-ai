"""
Briefing store — persists and queries BriefingItems written by background agents.
These items are the source of truth for the "what's the update?" briefing.
"""
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


async def add_item(
    category: str,
    title: str,
    summary: str,
    source_agent: str,
    priority: int = 5,
    meta: dict | None = None,
    ttl_hours: int = 24,
) -> str:
    """Write a briefing item to the DB. Returns its id."""
    from db.database import AsyncSessionLocal
    from db.models import BriefingItem

    expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
    async with AsyncSessionLocal() as db:
        item = BriefingItem(
            category=category,
            priority=priority,
            title=title,
            summary=summary,
            source_agent=source_agent,
            meta=meta or {},
            expires_at=expires_at,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item.id


async def get_unread(limit: int = 50) -> list[dict]:
    """Return unread, non-expired items sorted by priority then recency."""
    from db.database import AsyncSessionLocal
    from db.models import BriefingItem
    from sqlalchemy import select

    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        q = (
            select(BriefingItem)
            .where(BriefingItem.is_read == False)  # noqa: E712
            .where((BriefingItem.expires_at == None) | (BriefingItem.expires_at > now))
            .order_by(BriefingItem.priority.asc(), BriefingItem.created_at.desc())
            .limit(limit)
        )
        rows = (await db.execute(q)).scalars().all()
        return [_to_dict(r) for r in rows]


async def mark_read(item_ids: list[str]) -> None:
    """Mark items as read after the briefing delivers them."""
    from db.database import AsyncSessionLocal
    from db.models import BriefingItem
    from sqlalchemy import update

    if not item_ids:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(BriefingItem)
            .where(BriefingItem.id.in_(item_ids))
            .values(is_read=True)
        )
        await db.commit()


async def get_recent_by_category(category: str, limit: int = 5) -> list[dict]:
    from db.database import AsyncSessionLocal
    from db.models import BriefingItem
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        q = (
            select(BriefingItem)
            .where(BriefingItem.category == category)
            .order_by(BriefingItem.created_at.desc())
            .limit(limit)
        )
        rows = (await db.execute(q)).scalars().all()
        return [_to_dict(r) for r in rows]


def _to_dict(item) -> dict:
    return {
        "id": item.id,
        "category": item.category,
        "priority": item.priority,
        "title": item.title,
        "summary": item.summary,
        "source_agent": item.source_agent,
        "meta": item.meta or {},
        "is_read": item.is_read,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
