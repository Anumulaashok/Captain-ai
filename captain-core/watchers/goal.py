"""Goal watcher — daily review of goal progress."""
import logging
from datetime import datetime

from watchers.base import WatchEvent, WatcherBase

log = logging.getLogger(__name__)


class GoalWatcher(WatcherBase):
    id = "goal_watcher"
    name = "Goal Watcher"
    interval_minutes = 1440  # daily

    async def watch(self) -> list[WatchEvent]:
        from goals.store import goal_store

        events: list[WatchEvent] = []
        try:
            goals = await goal_store.list_goals(active_only=True)
            for goal in goals:
                progress = goal.get("progress", 0)
                target = goal.get("target_date")
                if target:
                    try:
                        due = datetime.fromisoformat(target.replace("Z", ""))
                        days_left = (due - datetime.utcnow()).days
                        if days_left <= 3 and progress < 0.8:
                            events.append(WatchEvent(
                                category="goals",
                                title=f"Goal at risk: {goal['title']}",
                                summary=(
                                    f"{int(progress * 100)}% complete with "
                                    f"{days_left} days remaining."
                                ),
                                priority=3,
                                meta={"goal_id": goal["id"]},
                                source=self.id,
                            ))
                    except Exception:
                        pass

                for blocker in goal.get("blockers", []):
                    events.append(WatchEvent(
                        category="goals",
                        title=f"Blocked: {blocker.get('title', 'Task')}",
                        summary=blocker.get("description", "Needs your input"),
                        priority=2,
                        meta={"goal_id": goal["id"]},
                        source=self.id,
                    ))
        except Exception as e:
            log.debug(f"Goal watcher: {e}")

        return events
