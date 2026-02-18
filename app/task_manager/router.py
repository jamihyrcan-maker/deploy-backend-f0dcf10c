from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth_roles.deps import require_role
from ..persistence.db import get_session
from ..persistence.models import Task, TaskStatus, TaskType
from ..realtime_bus.bus import publish_event_nowait

router = APIRouter(prefix="/task-manager", tags=["task-manager"])


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.post("/tasks", dependencies=[Depends(require_role("operator"))])
def create_task(
    title: str,
    task_type: TaskType = TaskType.NAVIGATE,
    target_kind: str = "POI",
    target_ref: str = "",
    notes: Optional[str] = None,
    release_at: Optional[datetime] = None,
    created_by: str = "operator",
    session: Session = Depends(get_session),
):
    now = datetime.now(timezone.utc)
    release_at_utc = _to_utc(release_at)
    status = TaskStatus.PENDING if (release_at_utc and release_at_utc > now) else TaskStatus.READY

    task = Task(
        title=title,
        task_type=task_type,
        target_kind=target_kind,
        target_ref=target_ref,
        notes=notes,
        release_at=release_at_utc,
        status=status,
        created_by=created_by,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    publish_event_nowait("task.created", {
        "task_id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "target_kind": task.target_kind,
        "target_ref": task.target_ref,
        "release_at": str(task.release_at) if task.release_at else None,
    }, source="task-manager")

    return task


@router.get("/tasks", dependencies=[Depends(require_role("monitor"))])
def list_tasks(limit: int = 50, offset: int = 0, session: Session = Depends(get_session)):
    stmt = select(Task).order_by(Task.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())


@router.get("/tasks/{task_id}", dependencies=[Depends(require_role("monitor"))])
def get_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/tasks/{task_id}", dependencies=[Depends(require_role("operator"))])
def update_task(
    task_id: int,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    target_kind: Optional[str] = None,
    target_ref: Optional[str] = None,
    release_at: Optional[datetime] = None,
    session: Session = Depends(get_session),
):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if title is not None:
        task.title = title
    if notes is not None:
        task.notes = notes
    if target_kind is not None:
        task.target_kind = target_kind
    if target_ref is not None:
        task.target_ref = target_ref
    if release_at is not None:
        now = datetime.now(timezone.utc)
        release_at_utc = _to_utc(release_at)
        task.release_at = release_at_utc
        if task.status in (TaskStatus.READY, TaskStatus.PENDING):
            task.status = TaskStatus.PENDING if (release_at_utc and release_at_utc > now) else TaskStatus.READY

    session.add(task)
    session.commit()
    session.refresh(task)

    publish_event_nowait("task.updated", {
        "task_id": task.id,
        "task_type": task.task_type,
        "status": task.status,
    }, source="task-manager")

    return task


@router.patch("/tasks/{task_id}/status", dependencies=[Depends(require_role("operator"))])
def set_status(task_id: int, status: TaskStatus, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = status
    session.add(task)
    session.commit()
    session.refresh(task)

    publish_event_nowait("task.status_changed", {
        "task_id": task.id,
        "status": task.status,
    }, source="task-manager")

    return task
