"""Goal hierarchy models."""
from enum import Enum
from pydantic import BaseModel, Field


class GoalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    AT_RISK = "at_risk"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class Blocker(BaseModel):
    title: str
    description: str = ""
    resolved: bool = False


class Checkpoint(BaseModel):
    step_index: int
    summary: str
    context_snapshot: dict = Field(default_factory=dict)
    created_at: str = ""


class Task(BaseModel):
    id: str = ""
    title: str
    status: TaskStatus = TaskStatus.PENDING
    blockers: list[Blocker] = Field(default_factory=list)
    assigned_agent: str | None = None
    checkpoints: list[Checkpoint] = Field(default_factory=list)


class Milestone(BaseModel):
    id: str = ""
    title: str
    due_date: str | None = None
    tasks: list[Task] = Field(default_factory=list)
    progress: float = 0.0


class Goal(BaseModel):
    id: str = ""
    title: str
    description: str = ""
    target_date: str | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    milestones: list[Milestone] = Field(default_factory=list)
    progress: float = 0.0
    blockers: list[Blocker] = Field(default_factory=list)
