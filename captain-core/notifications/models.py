"""Notification models."""
from enum import IntEnum
from pydantic import BaseModel, Field
from datetime import datetime


class NotificationPriority(IntEnum):
    URGENT = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


class Action(BaseModel):
    label: str
    action_type: str  # open_url | navigate | approve
    payload: dict = Field(default_factory=dict)


class Notification(BaseModel):
    id: str = ""
    priority: int = 3
    category: str = ""
    title: str = ""
    summary: str = ""
    actions: list[Action] = Field(default_factory=list)
    source_agent: str = ""
    created_at: datetime | None = None
    read: bool = False
    dismissed: bool = False
