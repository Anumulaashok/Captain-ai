"""
Background scheduler — runs agents on a cron schedule and writes results to briefing/store.py.
Uses APScheduler's AsyncIOScheduler, started in main.py lifespan.
"""
import asyncio
import logging
from datetime import datetime

log = logging.getLogger(__name__)


async def _run_agent_job(agent_id: str, message: str, conversation_id: str = "background") -> None:
    """
    Run a single agent as a background job, persisting the result as a TaskRecord.
    Errors are caught so a bad agent never kills the scheduler.
    """
    from agents.registry import agent_registry
    from agents.base import AgentTask
    from db.database import AsyncSessionLocal
    from db.models import TaskRecord

    agent = agent_registry.get(agent_id)
    if agent is None:
        log.warning(f"Scheduler: agent '{agent_id}' not found, skipping job")
        return

    task = AgentTask(
        agent_id=agent_id,
        intent=f"{agent_id}_task",
        user_message=message,
        context={"source": "scheduler"},
    )

    async with AsyncSessionLocal() as db:
        rec = TaskRecord(
            id=task.id,
            agent_id=agent_id,
            status="running",
            intent=f"{agent_id}_task",
            input={"message": message, "scheduled": True},
            started_at=datetime.utcnow(),
        )
        db.add(rec)
        await db.commit()

    try:
        result = await agent.run(task)
        status = "success" if result.success else "failed"
        async with AsyncSessionLocal() as db:
            row = await db.get(TaskRecord, task.id)
            if row:
                row.status = status
                row.output = {"response": result.response[:1000]}
                row.completed_at = datetime.utcnow()
                await db.commit()

        log.info(f"Scheduler job {agent_id} finished: {status}")
    except Exception as e:
        log.error(f"Scheduler job {agent_id} raised: {e}")
        async with AsyncSessionLocal() as db:
            row = await db.get(TaskRecord, task.id)
            if row:
                row.status = "failed"
                row.error = str(e)
                row.completed_at = datetime.utcnow()
                await db.commit()


# --------------------------------------------------------------------------- #
# Job definitions — every entry becomes a recurring APScheduler job.           #
# Intervals are conservative to stay within 16 GB RAM constraints.             #
# --------------------------------------------------------------------------- #
async def _speak_morning_briefing() -> None:
    """Called at 8am — proactively speaks the morning briefing."""
    try:
        from voice.engine import voice_engine
        await voice_engine.speak_briefing(conversation_id="morning_briefing")
    except Exception as e:
        log.error(f"Morning briefing failed: {e}")


SCHEDULED_JOBS = [
    {
        "id": "github_pr_check",
        "agent_id": "github",
        "message": "Check for open PRs awaiting my review and recent CI failures.",
        "trigger": "interval",
        "minutes": 30,
    },
    {
        "id": "email_inbox_scan",
        "agent_id": "email",
        "message": "Scan my inbox for new important emails and action items from the last hour.",
        "trigger": "interval",
        "minutes": 60,
    },
    {
        "id": "calendar_today",
        "agent_id": "calendar",
        "message": "List my events for today and flag any conflicts or upcoming deadlines.",
        "trigger": "cron",
        "hour": 8,
        "minute": 0,
    },
    {
        "id": "finance_weekly",
        "agent_id": "finance",
        "message": "Give me a spending summary for the last 7 days and flag any unusual transactions.",
        "trigger": "cron",
        "day_of_week": "mon",
        "hour": 9,
        "minute": 0,
    },
]

PROACTIVE_JOBS = [
    {
        "id": "morning_briefing",
        "func": "_speak_morning_briefing",
        "trigger": "cron",
        "hour": 8,
        "minute": 0,
    },
]


def build_scheduler():
    """Create and configure the AsyncIOScheduler. Call start() after the event loop is ready."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError:
        log.warning("APScheduler not installed — background jobs disabled. Run: pip install apscheduler")
        return None

    scheduler = AsyncIOScheduler()

    # Morning proactive briefing
    scheduler.add_job(
        _speak_morning_briefing,
        trigger="cron",
        id="morning_briefing",
        hour=8,
        minute=0,
        replace_existing=True,
    )
    log.info("Scheduled job 'morning_briefing' (cron 08:00)")

    for job in SCHEDULED_JOBS:
        trigger = job["trigger"]
        kwargs = {k: v for k, v in job.items()
                  if k not in ("id", "agent_id", "message", "trigger")}

        scheduler.add_job(
            _run_agent_job,
            trigger=trigger,
            id=job["id"],
            kwargs={"agent_id": job["agent_id"], "message": job["message"]},
            replace_existing=True,
            **kwargs,
        )
        log.info(f"Scheduled job '{job['id']}' ({trigger})")

    return scheduler


_scheduler = None


def get_scheduler():
    return _scheduler


def start_scheduler() -> None:
    global _scheduler
    _scheduler = build_scheduler()
    if _scheduler:
        _scheduler.start()
        log.info("Background scheduler started")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Background scheduler stopped")
