"""Goal persistence."""
import logging
import uuid

from goals.models import Goal, Milestone, Task, Blocker

log = logging.getLogger(__name__)


def _calc_progress(milestones: list) -> float:
    if not milestones:
        return 0.0
    total_tasks = 0
    completed = 0
    for ms in milestones:
        tasks = ms.get("tasks", []) if isinstance(ms, dict) else ms.tasks
        for t in tasks:
            total_tasks += 1
            status = t.get("status") if isinstance(t, dict) else t.status
            if status in ("completed", TaskStatus.COMPLETED):
                completed += 1
    return completed / total_tasks if total_tasks else 0.0


class GoalStore:
    async def create_goal(
        self,
        title: str,
        description: str = "",
        target_date: str | None = None,
        milestones: list | None = None,
    ) -> dict:
        from db.database import AsyncSessionLocal
        from db.models import GoalRecord

        goal_id = str(uuid.uuid4())
        ms_data = milestones or []
        progress = _calc_progress(ms_data)

        async with AsyncSessionLocal() as db:
            rec = GoalRecord(
                id=goal_id,
                title=title,
                description=description,
                target_date=target_date,
                status="active",
                progress=progress,
                milestones=ms_data,
                blockers=[],
            )
            db.add(rec)
            await db.commit()
        return await self.get_goal(goal_id)

    async def get_goal(self, goal_id: str) -> dict | None:
        from db.database import AsyncSessionLocal
        from db.models import GoalRecord

        async with AsyncSessionLocal() as db:
            rec = await db.get(GoalRecord, goal_id)
            if not rec:
                return None
            return self._to_dict(rec)

    async def list_goals(self, active_only: bool = True) -> list[dict]:
        from db.database import AsyncSessionLocal
        from db.models import GoalRecord
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            q = select(GoalRecord).order_by(GoalRecord.updated_at.desc())
            if active_only:
                q = q.where(GoalRecord.status == "active")
            rows = (await db.execute(q)).scalars().all()
            return [self._to_dict(r) for r in rows]

    async def update_goal(self, goal_id: str, **updates) -> dict | None:
        from db.database import AsyncSessionLocal
        from db.models import GoalRecord

        async with AsyncSessionLocal() as db:
            rec = await db.get(GoalRecord, goal_id)
            if not rec:
                return None
            for key, val in updates.items():
                if hasattr(rec, key):
                    setattr(rec, key, val)
            if "milestones" in updates:
                rec.progress = _calc_progress(updates["milestones"])
            await db.commit()
        return await self.get_goal(goal_id)

    async def add_blocker(self, goal_id: str, title: str, description: str = "") -> dict | None:
        goal = await self.get_goal(goal_id)
        if not goal:
            return None
        blockers = goal.get("blockers", [])
        blockers.append({"title": title, "description": description, "resolved": False})
        return await self.update_goal(goal_id, blockers=blockers)

    def _to_dict(self, rec) -> dict:
        return {
            "id": rec.id,
            "title": rec.title,
            "description": rec.description or "",
            "target_date": rec.target_date,
            "status": rec.status,
            "progress": rec.progress or 0.0,
            "milestones": rec.milestones or [],
            "blockers": rec.blockers or [],
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        }


goal_store = GoalStore()
