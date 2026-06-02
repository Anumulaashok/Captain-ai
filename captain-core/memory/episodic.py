"""Episodic memory — conversation history stored in Neon PostgreSQL."""
import uuid
import logging
from datetime import datetime

from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from db.database import AsyncSessionLocal
from db.models import Conversation, Message
from memory.schemas import MessageContext

log = logging.getLogger(__name__)


class EpisodicMemory:

    async def create_conversation(
        self, model_id: str | None = None, agent_id: str | None = None
    ) -> str:
        conv_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            conv = Conversation(id=conv_id, model_id=model_id, agent_id=agent_id)
            db.add(conv)
            await db.commit()
        return conv_id

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tokens_used: int | None = None,
        latency_ms: int | None = None,
        meta: dict | None = None,
    ) -> str:
        msg_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            msg = Message(
                id=msg_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                meta=meta,
            )
            db.add(msg)
            # Update conversation updated_at
            result = await db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one_or_none()
            if conv:
                conv.updated_at = datetime.utcnow()
                if not conv.title and role == "user":
                    conv.title = content[:60] + ("…" if len(content) > 60 else "")
            await db.commit()
        return msg_id

    async def get_recent_messages(
        self, conversation_id: str, n: int = 20
    ) -> list[MessageContext]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(desc(Message.created_at))
                .limit(n)
            )
            msgs = result.scalars().all()
        return [
            MessageContext(role=m.role, content=m.content, created_at=m.created_at)
            for m in reversed(msgs)
        ]

    async def get_conversation(self, conversation_id: str) -> dict | None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Conversation)
                .options(selectinload(Conversation.messages))
                .where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one_or_none()
        if not conv:
            return None
        return {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
            "model_id": conv.model_id,
            "agent_id": conv.agent_id,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat(),
                    "tokens_used": m.tokens_used,
                    "latency_ms": m.latency_ms,
                    "meta": m.meta,
                }
                for m in conv.messages
            ],
        }

    async def list_conversations(self, limit: int = 50) -> list[dict]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Conversation).order_by(desc(Conversation.updated_at)).limit(limit)
            )
            convs = result.scalars().all()
        return [
            {
                "id": c.id,
                "title": c.title or "New conversation",
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
                "model_id": c.model_id,
            }
            for c in convs
        ]

    async def delete_conversation(self, conversation_id: str) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one_or_none()
            if conv:
                await db.delete(conv)
                await db.commit()

    async def update_title(self, conversation_id: str, title: str) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one_or_none()
            if conv:
                conv.title = title
                await db.commit()


episodic_memory = EpisodicMemory()
