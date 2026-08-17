"""Track agent success rates and failure patterns."""
import logging
import uuid
from collections import defaultdict

log = logging.getLogger(__name__)


class MetricsTracker:
    async def record_run(
        self,
        agent_id: str,
        task_id: str,
        success: bool,
        latency_ms: int = 0,
        error: str | None = None,
        user_rating: int | None = None,
    ) -> None:
        from db.database import AsyncSessionLocal
        from db.models import AgentMetricRecord

        async with AsyncSessionLocal() as db:
            rec = AgentMetricRecord(
                id=str(uuid.uuid4()),
                agent_id=agent_id,
                task_id=task_id,
                success=success,
                latency_ms=latency_ms,
                error=error,
                user_rating=user_rating,
            )
            db.add(rec)
            await db.commit()

    async def get_agent_stats(self, agent_id: str) -> dict:
        from db.database import AsyncSessionLocal
        from db.models import AgentMetricRecord
        from sqlalchemy import select, func

        async with AsyncSessionLocal() as db:
            q = select(AgentMetricRecord).where(AgentMetricRecord.agent_id == agent_id)
            rows = (await db.execute(q)).scalars().all()

        if not rows:
            return {"agent_id": agent_id, "total_runs": 0, "success_rate": 0.0}

        successes = sum(1 for r in rows if r.success)
        errors = [r.error for r in rows if r.error]
        error_counts = defaultdict(int)
        for e in errors:
            error_counts[e[:100]] += 1

        return {
            "agent_id": agent_id,
            "total_runs": len(rows),
            "success_rate": successes / len(rows),
            "avg_latency_ms": sum(r.latency_ms or 0 for r in rows) / len(rows),
            "error_patterns": sorted(error_counts.items(), key=lambda x: -x[1])[:5],
        }

    async def get_all_stats(self) -> list[dict]:
        from agents.registry import agent_registry
        agents = agent_registry.list_all()
        return [await self.get_agent_stats(a.id) for a in agents]


metrics_tracker = MetricsTracker()
