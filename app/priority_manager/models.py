from __future__ import annotations

from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskPriorityOverride(SQLModel, table=True):
    """
    Operator override stored separately (no need to change Task table).
    One row per task_id.
    """
    task_id: int = Field(primary_key=True)
    override: int = Field(default=0, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)
