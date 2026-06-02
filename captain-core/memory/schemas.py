from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class MemoryEntrySchema(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str  # fact | preference | entity | event
    key: str | None = None
    value: str
    source: str | None = None  # conversation_id or agent_id
    pinecone_id: str | None = None
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None


class MessageContext(BaseModel):
    role: str
    content: str
    created_at: datetime | None = None


class ConversationContext(BaseModel):
    conversation_id: str
    recent_messages: list[MessageContext] = []
    retrieved_memories: list[MemoryEntrySchema] = []
    user_preferences: dict = {}


class RetrievalResult(BaseModel):
    memories: list[MemoryEntrySchema]
    scores: list[float]
    query: str
