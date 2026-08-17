"""Goals API."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class CreateGoalRequest(BaseModel):
    title: str
    description: str = ""
    target_date: str | None = None


class FeedbackRequest(BaseModel):
    conversation_id: str
    rating: int
    comment: str = ""


@router.get("/goals")
async def list_goals(active_only: bool = True):
    from goals.store import goal_store
    return await goal_store.list_goals(active_only=active_only)


@router.post("/goals")
async def create_goal(req: CreateGoalRequest):
    from goals.store import goal_store
    return await goal_store.create_goal(req.title, req.description, req.target_date)


@router.get("/goals/{goal_id}")
async def get_goal(goal_id: str):
    from goals.store import goal_store
    goal = await goal_store.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.get("/tasks/long-running")
async def list_long_running_tasks():
    from goals.executor import task_executor
    return await task_executor.list_pending()


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    from learning.engine import learning_engine
    await learning_engine.record_feedback(req.conversation_id, req.rating, req.comment)
    return {"ok": True}


@router.get("/metrics/agents")
async def get_agent_metrics():
    from metrics.tracker import metrics_tracker
    return await metrics_tracker.get_all_stats()


@router.get("/metrics/improvements")
async def get_improvement_suggestions():
    from metrics.improve import improvement_engine
    return await improvement_engine.get_suggestions()
