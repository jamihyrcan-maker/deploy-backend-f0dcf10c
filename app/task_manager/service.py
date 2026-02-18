from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, select

from ..persistence.models import Task, TaskStatus, TaskType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_dt(dt: Optional[datetime]) -> Optional[datetime]:
    """If user sends naive datetime, assume it's UTC (v0)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class TaskManagerService:
    """
    Task Manager v0:
      - Create tasks with instant vs delayed scheduling (release_at)
      - List tasks with simple filters
      - Read one task
      - Update task fields
      - Update status (CANCEL / DONE / etc.)
    """

    def __init__(self, session: Session):
        self.session = session

    def create_task(
        self,
        *,
        title: str,
        notes: Optional[str],
        task_type: TaskType,
        target_kind: str,
        target_ref: str,
        release_at: Optional[datetime],
        created_by: Optional[str],
    ) -> Task:
        now = utc_now()
        release_at = _normalize_dt(release_at)

        status = TaskStatus.READY
        if release_at and release_at > now:
            status = TaskStatus.PENDING

        task = Task(
            title=title,
            notes=notes,
            task_type=task_type,
            target_kind=target_kind,
            target_ref=target_ref,
            release_at=release_at,
            status=status,
            created_by=created_by or "operator",
            created_at=now,
            updated_at=now,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def get_task(self, task_id: int) -> Optional[Task]:
        return self.session.get(Task, task_id)

    def list_tasks(
        self,
        *,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
        limit: int = 50,
        offset: int = 0,
        newest_first: bool = True,
    ) -> List[Task]:
        stmt = select(Task)

        if status:
            stmt = stmt.where(Task.status == status)
        if task_type:
            stmt = stmt.where(Task.task_type == task_type)

        stmt = stmt.order_by(Task.created_at.desc() if newest_first else Task.created_at.asc())
        stmt = stmt.offset(offset).limit(limit)

        return list(self.session.exec(stmt).all())

    def update_task_fields(
        self,
        task: Task,
        *,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        target_kind: Optional[str] = None,
        target_ref: Optional[str] = None,
        release_at: Optional[datetime] = None,
    ) -> Task:
        now = utc_now()

        if title is not None:
            task.title = title
        if notes is not None:
            task.notes = notes
        if task_type is not None:
            task.task_type = task_type
        if target_kind is not None:
            task.target_kind = target_kind
        if target_ref is not None:
            task.target_ref = target_ref

        if release_at is not None:
            release_at = _normalize_dt(release_at)
            task.release_at = release_at

            # If task is still pending/ready, re-evaluate based on new release time
            if task.status in (TaskStatus.PENDING, TaskStatus.READY):
                if release_at and release_at > now:
                    task.status = TaskStatus.PENDING
                else:
                    task.status = TaskStatus.READY

        task.updated_at = now
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def set_status(self, task: Task, new_status: TaskStatus) -> Task:
        task.status = new_status
        task.updated_at = utc_now()
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task
