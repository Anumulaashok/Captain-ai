"""Watcher scheduler — runs all watchers on interval."""
import asyncio
import logging

log = logging.getLogger(__name__)


class WatcherScheduler:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._watchers = []

    def _load_watchers(self):
        if self._watchers:
            return
        from watchers.gmail import GmailWatcher
        from watchers.github import GitHubWatcher
        from watchers.goal import GoalWatcher
        self._watchers = [GmailWatcher(), GitHubWatcher(), GoalWatcher()]

    async def _tick(self):
        from notifications.store import notification_store
        from api.websocket import event_bus

        self._load_watchers()
        for watcher in self._watchers:
            events = await watcher.run()
            for event in events:
                notif_id = await notification_store.add(
                    category=event.category,
                    title=event.title,
                    summary=event.summary,
                    priority=event.priority,
                    source_agent=event.source or watcher.id,
                    meta=event.meta,
                )
                await event_bus.publish("notification", {
                    "id": notif_id,
                    "category": event.category,
                    "title": event.title,
                    "summary": event.summary,
                    "priority": event.priority,
                    "source_agent": event.source,
                })

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                log.error(f"Watcher tick error: {e}")
            await asyncio.sleep(60)  # check every minute

    def start(self):
        if self._running:
            return
        self._running = True
        try:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(self._loop())
        except RuntimeError:
            pass

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None


watcher_scheduler = WatcherScheduler()
