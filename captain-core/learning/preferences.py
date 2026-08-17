"""Preference inference from interaction patterns."""
import logging
from collections import Counter

log = logging.getLogger(__name__)


async def infer_communication_style() -> dict:
    """Infer if user prefers brief or detailed responses."""
    from db.database import AsyncSessionLocal
    from db.models import InteractionLog
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        q = select(InteractionLog).order_by(InteractionLog.created_at.desc()).limit(50)
        rows = (await db.execute(q)).scalars().all()

    if not rows:
        return {"style": "balanced", "confidence": 0.0}

    positive = sum(1 for r in rows if r.accepted is True)
    negative = sum(1 for r in rows if r.accepted is False)
    total = positive + negative

    if total < 3:
        return {"style": "balanced", "confidence": 0.3}

    return {
        "style": "concise" if positive > negative * 1.5 else "detailed",
        "confidence": min(1.0, total / 20),
        "positive_rate": positive / total if total else 0,
    }


async def infer_sender_importance() -> dict[str, float]:
    """Learn which senders/topics user cares about from feedback."""
    from memory.preferences import preference_store
    stored = await preference_store.get("important_senders")
    return stored if isinstance(stored, dict) else {}
