from __future__ import annotations

from datetime import datetime, timezone
from sqlmodel import Session

from .models import TaskPriorityOverride


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PriorityService:
    @staticmethod
    def set_override(session: Session, task_id: int, override: int) -> TaskPriorityOverride:
        row = session.get(TaskPriorityOverride, task_id)
        if row is None:
            row = TaskPriorityOverride(task_id=task_id, override=override, updated_at=utc_now())
        else:
            row.override = override
            row.updated_at = utc_now()

        session.add(row)
        session.commit()
        session.refresh(row)
        return row

    @staticmethod
    def clear_override(session: Session, task_id: int) -> bool:
        row = session.get(TaskPriorityOverride, task_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True

    @staticmethod
    def get_override(session: Session, task_id: int) -> int:
        row = session.get(TaskPriorityOverride, task_id)
        return int(row.override) if row else 0
