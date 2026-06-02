import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from orchestrator.orchestrator import orchestrator
from memory.episodic import episodic_memory

log = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ConversationCreateRequest(BaseModel):
    model_id: str | None = None


@router.post("/chat")
async def chat(req: ChatRequest):
    """Stream a chat response via SSE."""
    conversation_id = req.conversation_id
    if not conversation_id:
        from config import settings
        conversation_id = await episodic_memory.create_conversation(
            model_id=settings.active_model_id
        )

    async def event_stream():
        # First event: conversation_id so client can track it
        yield f"data: {json.dumps({'type': 'conversation_id', 'data': {'id': conversation_id}})}\n\n"

        async for event in orchestrator.process(req.message, conversation_id):
            yield f"data: {json.dumps(event)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/conversations")
async def list_conversations(limit: int = 50):
    return await episodic_memory.list_conversations(limit=limit)


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    conv = await episodic_memory.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    await episodic_memory.delete_conversation(conversation_id)
    return {"ok": True}


@router.post("/conversations")
async def create_conversation(req: ConversationCreateRequest):
    conv_id = await episodic_memory.create_conversation(model_id=req.model_id)
    return {"id": conv_id}
