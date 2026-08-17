"""Interaction logger for learning."""
import logging
import uuid

log = logging.getLogger(__name__)


async def log_interaction(
    user_message: str,
    agent_id: str | None = None,
    conversation_id: str | None = None,
    accepted: bool | None = None,
    feedback: str | None = None,
    meta: dict | None = None,
) -> str:
    from db.database import AsyncSessionLocal
    from db.models import InteractionLog

    entry_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        entry = InteractionLog(
            id=entry_id,
            conversation_id=conversation_id,
            user_message=user_message[:2000],
            agent_id=agent_id,
            accepted=accepted,
            feedback=feedback,
            meta=meta or {},
        )
        db.add(entry)
        await db.commit()
    return entry_id
