"""WebSocket event bus — pub/sub for real-time UI updates."""
import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)
router = APIRouter()


class EventBus:
    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._handlers: dict[str, list] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        log.debug(f"WS connected — total: {len(self._connections)}")

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def publish(self, event_type: str, data: Any) -> None:
        """Broadcast event to all connected WebSocket clients."""
        message = json.dumps({"type": event_type, "data": data})
        dead = set()
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.discard(ws)

        # Call internal subscribers
        for handler in self._handlers.get(event_type, []):
            try:
                await handler(data)
            except Exception as e:
                log.error(f"Event handler error ({event_type}): {e}")

    def subscribe(self, event_type: str, handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)


event_bus = EventBus()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await event_bus.connect(websocket)
    try:
        while True:
            # Receive client events (e.g. push-to-talk trigger)
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                event_type = msg.get("type")
                if event_type == "push_to_talk_start":
                    from voice.engine import voice_engine
                    await voice_engine.push_to_talk_start()
                elif event_type == "push_to_talk_stop":
                    from voice.engine import voice_engine
                    await voice_engine.push_to_talk_stop()
                elif event_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        event_bus.disconnect(websocket)
