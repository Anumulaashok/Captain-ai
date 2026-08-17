"""Notification persistence."""
import logging
import uuid
from datetime import datetime, timedelta

from notifications.priority import calculate_priority

log = logging.getLogger(__name__)


class NotificationStore:
    async def add(
        self,
        category: str,
        title: str,
        summary: str,
        priority: int | None = None,
        source_agent: str = "",
        meta: dict | None = None,
        ttl_hours: int = 48,
    ) -> str:
        from db.database import AsyncSessionLocal
        from db.models import BriefingItem

        if priority is None:
            priority = calculate_priority(title, summary, category)

        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
        item_id = str(uuid.uuid4())

        async with AsyncSessionLocal() as db:
            item = BriefingItem(
                id=item_id,
                category=category,
                priority=priority,
                title=title,
                summary=summary,
                source_agent=source_agent,
                meta={**(meta or {}), "notification": True},
                expires_at=expires_at,
            )
            db.add(item)
            await db.commit()

        return item_id

    async def list_notifications(
        self, unread_only: bool = True, limit: int = 50
    ) -> list[dict]:
        from briefing import store as briefing_store
        items = await briefing_store.get_unread(limit=limit)
        if not unread_only:
            from db.database import AsyncSessionLocal
            from db.models import BriefingItem
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                q = (
                    select(BriefingItem)
                    .order_by(BriefingItem.priority.asc(), BriefingItem.created_at.desc())
                    .limit(limit)
                )
                rows = (await db.execute(q)).scalars().all()
                return [briefing_store._to_dict(r) for r in rows]
        return items

    async def mark_read(self, item_ids: list[str]) -> None:
        from briefing import store as briefing_store
        await briefing_store.mark_read(item_ids)

    async def dismiss(self, item_id: str) -> None:
        from db.database import AsyncSessionLocal
        from db.models import BriefingItem
        async with AsyncSessionLocal() as db:
            item = await db.get(BriefingItem, item_id)
            if item:
                item.is_read = True
                if item.meta:
                    item.meta = {**item.meta, "dismissed": True}
                await db.commit()


notification_store = NotificationStore()
