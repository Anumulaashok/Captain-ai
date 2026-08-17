"""Multi-day task executor with checkpoints."""
import logging
import uuid
from datetime import datetime

log = logging.getLogger(__name__)


class TaskExecutor:
    async def create_task(
        self,
        description: str,
        steps: list[str] | None = None,
        goal_id: str | None = None,
    ) -> dict:
        from db.database import AsyncSessionLocal
        from db.models import LongRunningTaskRecord

        task_id = str(uuid.uuid4())
        step_objs = [
            {"index": i, "description": s, "status": "pending"}
            for i, s in enumerate(steps or [description])
        ]

        async with AsyncSessionLocal() as db:
            rec = LongRunningTaskRecord(
                id=task_id,
                goal_id=goal_id,
                description=description,
                status="pending",
                steps=step_objs,
                current_step=0,
                checkpoints=[],
                blockers=[],
                context={},
            )
            db.add(rec)
            await db.commit()
        return await self.get_task(task_id)

    async def get_task(self, task_id: str) -> dict | None:
        from db.database import AsyncSessionLocal
        from db.models import LongRunningTaskRecord

        async with AsyncSessionLocal() as db:
            rec = await db.get(LongRunningTaskRecord, task_id)
            if not rec:
                return None
            return self._to_dict(rec)

    async def save_checkpoint(
        self, task_id: str, summary: str, context: dict | None = None
    ) -> dict | None:
        from db.database import AsyncSessionLocal
        from db.models import LongRunningTaskRecord

        async with AsyncSessionLocal() as db:
            rec = await db.get(LongRunningTaskRecord, task_id)
            if not rec:
                return None
            checkpoints = list(rec.checkpoints or [])
            checkpoints.append({
                "step_index": rec.current_step,
                "summary": summary,
                "context_snapshot": context or {},
                "created_at": datetime.utcnow().isoformat(),
            })
            rec.checkpoints = checkpoints
            rec.status = "in_progress"
            if context:
                rec.context = {**(rec.context or {}), **context}
            await db.commit()
        return await self.get_task(task_id)

    async def advance_step(self, task_id: str) -> dict | None:
        from db.database import AsyncSessionLocal
        from db.models import LongRunningTaskRecord

        async with AsyncSessionLocal() as db:
            rec = await db.get(LongRunningTaskRecord, task_id)
            if not rec:
                return None
            steps = rec.steps or []
            if rec.current_step < len(steps):
                steps[rec.current_step]["status"] = "completed"
                rec.current_step += 1
            if rec.current_step >= len(steps):
                rec.status = "completed"
            else:
                rec.status = "in_progress"
            rec.steps = steps
            await db.commit()
        return await self.get_task(task_id)

    async def add_blocker(
        self, task_id: str, title: str, description: str = ""
    ) -> dict | None:
        from db.database import AsyncSessionLocal
        from db.models import LongRunningTaskRecord

        async with AsyncSessionLocal() as db:
            rec = await db.get(LongRunningTaskRecord, task_id)
            if not rec:
                return None
            blockers = list(rec.blockers or [])
            blockers.append({"title": title, "description": description})
            rec.blockers = blockers
            rec.status = "blocked"
            await db.commit()
        return await self.get_task(task_id)

    async def list_pending(self) -> list[dict]:
        from db.database import AsyncSessionLocal
        from db.models import LongRunningTaskRecord
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            q = (
                select(LongRunningTaskRecord)
                .where(LongRunningTaskRecord.status.in_(["pending", "in_progress", "blocked"]))
                .order_by(LongRunningTaskRecord.updated_at.desc())
            )
            rows = (await db.execute(q)).scalars().all()
            return [self._to_dict(r) for r in rows]

    def _to_dict(self, rec) -> dict:
        return {
            "id": rec.id,
            "goal_id": rec.goal_id,
            "description": rec.description,
            "status": rec.status,
            "steps": rec.steps or [],
            "current_step": rec.current_step,
            "checkpoints": rec.checkpoints or [],
            "blockers": rec.blockers or [],
            "context": rec.context or {},
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        }


task_executor = TaskExecutor()
