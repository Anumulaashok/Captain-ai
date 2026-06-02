"""User preference store backed by Neon PostgreSQL."""
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from db.database import AsyncSessionLocal
from db.models import Preference

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "ui_theme": "system",          # light | dark | system
    "font_size": "medium",
    "voice_enabled": False,
    "voice_mode": "wake_word",     # wake_word | push_to_talk | continuous | disabled
    "voice_tts_enabled": True,
    "active_model": "",   # resolved at startup from Ollama
    "show_agent_activity": True,
    "notification_chat": True,
    "notification_agent_done": True,
    "memory_auto_consolidate": True,
    "memory_consolidate_after_n": 10,
    "agent_permissions": {},
    "sidebar_width": 260,
    "code_theme": "github-dark",
}


class PreferenceStore:

    async def get(self, key: str, default: Any = None) -> Any:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Preference).where(Preference.key == key))
            pref = result.scalar_one_or_none()
        if pref is not None:
            return pref.value
        return DEFAULTS.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Preference).where(Preference.key == key))
            pref = result.scalar_one_or_none()
            if pref:
                pref.value = value
                pref.updated_at = datetime.utcnow()
            else:
                db.add(Preference(key=key, value=value))
            await db.commit()

    async def delete(self, key: str) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Preference).where(Preference.key == key))
            pref = result.scalar_one_or_none()
            if pref:
                await db.delete(pref)
                await db.commit()

    async def get_all(self) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Preference))
            prefs = {p.key: p.value for p in result.scalars().all()}
        return {**DEFAULTS, **prefs}

    async def update_many(self, updates: dict[str, Any]) -> None:
        for key, value in updates.items():
            await self.set(key, value)


preference_store = PreferenceStore()
