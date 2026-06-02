"""
Runtime permission approval manager.

When an agent needs a permission it doesn't currently have, it calls
`approval_manager.request(...)` which:
  1. Publishes a `permission_request` event over the WebSocket EventBus.
  2. Suspends the agent (awaits a Future).
  3. The UI shows an Approve / Deny modal and POSTs to /api/agents/approvals/{request_id}.
  4. `resolve()` sets the Future; the agent continues or gets a denial error.
"""
import asyncio
import logging
import uuid
from datetime import datetime

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 120  # 2 minutes before auto-deny


class ApprovalManager:
    def __init__(self):
        # request_id → asyncio.Future[bool]
        self._pending: dict[str, asyncio.Future] = {}

    async def request(
        self,
        agent_id: str,
        permission: str,
        reason: str = "",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> bool:
        """
        Pause the caller until the user approves or denies.
        Returns True if approved, False if denied or timed out.
        """
        from api.websocket import event_bus

        request_id = str(uuid.uuid4())
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        # Push the request to all connected UI clients
        await event_bus.publish("permission_request", {
            "request_id": request_id,
            "agent_id": agent_id,
            "permission": permission,
            "reason": reason or f"{agent_id} needs access to {permission}",
            "requested_at": datetime.utcnow().isoformat(),
            "timeout_seconds": timeout,
        })

        log.info(f"Permission request {request_id}: {agent_id} wants {permission}")

        try:
            approved = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            log.warning(f"Permission request {request_id} timed out — denying")
            approved = False
        finally:
            self._pending.pop(request_id, None)

        log.info(f"Permission request {request_id}: {'approved' if approved else 'denied'}")
        return approved

    def resolve(self, request_id: str, approved: bool) -> bool:
        """
        Called by the API endpoint when the user clicks Approve or Deny.
        Returns False if the request_id is unknown (already timed out, etc.).
        """
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(approved)
        return True

    def list_pending(self) -> list[str]:
        return list(self._pending.keys())


approval_manager = ApprovalManager()
