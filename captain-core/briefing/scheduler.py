"""Scheduled morning briefing and end-of-day summary."""
import asyncio
import logging
from datetime import datetime

log = logging.getLogger(__name__)


class BriefingScheduler:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_morning: str | None = None
        self._last_eod: str | None = None

    async def _generate_briefing(self, briefing_type: str) -> str:
        from briefing.generator import generate_briefing
        return await generate_briefing(briefing_type)

    async def _tick(self):
        from memory.preferences import preference_store
        from api.websocket import event_bus

        prefs = await preference_store.get_all()
        morning_hour = int(prefs.get("briefing_morning_hour", 8))
        eod_hour = int(prefs.get("briefing_eod_hour", 18))
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        if now.hour == morning_hour and self._last_morning != today:
            text = await self._generate_briefing("morning")
            await event_bus.publish("briefing", {"type": "morning", "text": text})
            self._last_morning = today
            log.info("Morning briefing generated")

        if now.hour == eod_hour and self._last_eod != today:
            text = await self._generate_briefing("eod")
            await event_bus.publish("briefing", {"type": "eod", "text": text})
            self._last_eod = today
            log.info("End-of-day summary generated")

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                log.error(f"Briefing scheduler error: {e}")
            await asyncio.sleep(300)  # check every 5 min

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


briefing_scheduler = BriefingScheduler()
