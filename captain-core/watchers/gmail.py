"""Gmail watcher — monitors inbox for important emails."""
import logging

from watchers.base import WatchEvent, WatcherBase

log = logging.getLogger(__name__)

URGENT_KEYWORDS = {"urgent", "asap", "deadline", "action required", "immediate"}
IMPORTANT_SENDERS_KEY = "important_senders"


class GmailWatcher(WatcherBase):
    id = "gmail_watcher"
    name = "Gmail Watcher"
    interval_minutes = 15

    async def watch(self) -> list[WatchEvent]:
        from integrations.credentials import credentials_store

        if not await credentials_store.has_valid_token("gmail"):
            return []

        events: list[WatchEvent] = []
        try:
            from agents.gmail.agent import Agent
            agent = Agent()
            result = await agent._api_list_inbox(10, unread_only=True)
            if not result or result == "Inbox is empty.":
                return []

            last_id = self.state.get("last_notified_id")
            for block in result.split("\n\n"):
                if not block.strip():
                    continue
                lines = block.split("\n")
                msg_id = ""
                for line in lines:
                    if line.startswith("["):
                        msg_id = line.split("]")[0].strip("[")
                        break
                if msg_id and msg_id == last_id:
                    continue

                text_lower = block.lower()
                priority = 7
                if any(kw in text_lower for kw in URGENT_KEYWORDS):
                    priority = 2
                elif "unread" in text_lower:
                    priority = 4

                subject = ""
                for line in lines:
                    if "Subject:" in line:
                        subject = line.split("Subject:", 1)[-1].strip()
                        break

                events.append(WatchEvent(
                    category="email",
                    title=f"New email: {subject[:80] or 'Unread message'}",
                    summary=block[:300],
                    priority=priority,
                    meta={"message_id": msg_id},
                    source=self.id,
                ))
                if msg_id:
                    self.state["last_notified_id"] = msg_id

        except Exception as e:
            log.debug(f"Gmail watcher: {e}")

        return events[:5]
