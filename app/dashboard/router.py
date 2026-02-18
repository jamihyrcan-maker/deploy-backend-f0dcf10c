from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..persistence.db import get_session
from ..robot_api.router import get_robot_api_service
from ..robot_api.service import RobotAPIService
from ..workflow_engine.vendor_task_client import AutoXingTaskClient
from ..workflow_engine.router import get_task_client

from ..queue_manager.service import QueueManagerService
from ..assignment_engine.service import AssignmentEngineService
from ..persistence.models import Task, TaskStatus, WorkflowRun, WorkflowRunStatus, WorkflowStep
from ..auth_roles.deps import require_role


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", dependencies=[Depends(require_role("monitor"))])
async def overview(
    session: Session = Depends(get_session),
    robot_api: RobotAPIService = Depends(get_robot_api_service),
    task_client: AutoXingTaskClient = Depends(get_task_client),
    limit: int = 200,
    offset: int = 0,
):
    ae = AssignmentEngineService(session, robot_api, task_client)
    robots = await ae.list_robots(include_state=False)

    qm = QueueManagerService(session)
    ready_queue = qm.get_ready_queue()
    stats = qm.stats()

    runs_stmt = select(WorkflowRun).where(WorkflowRun.status == WorkflowRunStatus.RUNNING).order_by(WorkflowRun.updated_at.desc())
    runs = list(session.exec(runs_stmt).all())

    items: List[Dict[str, Any]] = []
    for r in runs:
        steps_stmt = select(WorkflowStep).where(WorkflowStep.run_id == r.id).order_by(WorkflowStep.step_index.asc())
        steps = list(session.exec(steps_stmt).all())
        current = next((s for s in steps if s.step_index == r.current_step_index), None)

        items.append({
            "run_id": r.id,
            "task_id": r.task_id,
            "robot_id": r.robot_id,
            "status": r.status,
            "current_step_index": r.current_step_index,
            "total_steps": r.total_steps,
            "current_vendor_task_id": r.current_vendor_task_id,
            "last_error": r.last_error,
            "current_step": None if current is None else {
                "step_index": current.step_index,
                "step_type": current.step_type,
                "step_code": current.step_code,
                "label": current.label,
                "decision": current.decision,
                "completed_at": current.completed_at,
            }
        })

    task_stmt = select(Task).order_by(Task.created_at.desc()).offset(offset).limit(limit)
    tasks = list(session.exec(task_stmt).all())
    task_ids = [t.id for t in tasks if t.id is not None]

    started_at_by_task: Dict[int, Any] = {}
    if task_ids:
        runs_for_tasks = list(
            session.exec(
                select(WorkflowRun)
                .where(WorkflowRun.task_id.in_(task_ids))
                .order_by(WorkflowRun.created_at.asc())
            ).all()
        )
        for r in runs_for_tasks:
            if r.task_id not in started_at_by_task:
                started_at_by_task[r.task_id] = r.created_at

    task_rows: List[Dict[str, Any]] = []
    for t in tasks:
        finished_at = t.updated_at if t.status in (TaskStatus.DONE, TaskStatus.CANCELED) else None
        task_rows.append({
            "task_id": t.id,
            "status": t.status,
            "task_type": t.task_type,
            "title": t.title,
            "target_kind": t.target_kind,
            "target_ref": t.target_ref,
            "created_at": t.created_at,
            "release_at": t.release_at,
            "updated_at": t.updated_at,
            "assigned_robot_id": t.assigned_robot_id,
            "started_at": started_at_by_task.get(t.id),
            "finished_at": finished_at,
        })

    return {
        "robots": robots,
        "queue_ready": ready_queue,
        "task_stats": stats,
        "running_workflows": items,
        "tasks": task_rows,
    }
