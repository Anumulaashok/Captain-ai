"""Base watcher class for background monitoring."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class WatchEvent(BaseModel):
    category: str
    title: str
    summary: str
    priority: int = 5  # 1=urgent … 10=low
    meta: dict = Field(default_factory=dict)
    source: str = ""


class WatcherBase(ABC):
    id: str = ""
    name: str = ""
    interval_minutes: int = 15
    last_run: datetime | None = None
    state: dict[str, Any] = {}

    @abstractmethod
    async def watch(self) -> list[WatchEvent]:
        ...

    async def should_alert(self, event: WatchEvent) -> bool:
        return event.priority <= 5

    def is_due(self) -> bool:
        if self.last_run is None:
            return True
        return datetime.utcnow() - self.last_run >= timedelta(minutes=self.interval_minutes)

    async def run(self) -> list[WatchEvent]:
        if not self.is_due():
            return []
        try:
            events = await self.watch()
            self.last_run = datetime.utcnow()
            return [e for e in events if await self.should_alert(e)]
        except Exception as e:
            log.error(f"Watcher {self.id} failed: {e}")
            return []
