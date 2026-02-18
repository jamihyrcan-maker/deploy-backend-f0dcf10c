from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from ..persistence.models import TaskStatus, TaskType


class QueueItem(BaseModel):
    position: int
    task_id: int
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


class QueueResponse(BaseModel):
    items: List[QueueItem]
    total: int


class TickResponse(BaseModel):
    promoted: int


class QueueStats(BaseModel):
    pending: int
    ready: int
    assigned: int
    done: int
    canceled: int
