from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field as PydField

from ..persistence.models import TaskStatus, TaskType


class TaskCreate(BaseModel):
    title: str = PydField(..., min_length=1, max_length=200)
    notes: Optional[str] = None

    task_type: TaskType = TaskType.NAVIGATE

    target_kind: str = PydField(default="POI", max_length=50)
    target_ref: str = PydField(default="", max_length=200)

    # If release_at is in the future -> PENDING, else -> READY
    # Recommended: send ISO datetime with timezone (e.g., 2025-12-30T12:00:00+04:00)
    release_at: Optional[datetime] = None

    created_by: Optional[str] = "operator"


class TaskUpdate(BaseModel):
    title: Optional[str] = PydField(default=None, min_length=1, max_length=200)
    notes: Optional[str] = None

    task_type: Optional[TaskType] = None
    target_kind: Optional[str] = PydField(default=None, max_length=50)
    target_ref: Optional[str] = PydField(default=None, max_length=200)

    release_at: Optional[datetime] = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime

    status: TaskStatus
    task_type: TaskType

    title: str
    notes: Optional[str]

    target_kind: str
    target_ref: str

    release_at: Optional[datetime]
    assigned_robot_id: Optional[str]
    created_by: Optional[str]
