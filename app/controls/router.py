from __future__ import annotations

from typing import Optional
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, delete

from ..auth_roles.deps import require_role
from ..persistence.db import get_session
from ..persistence.models import Task, TaskStatus, WorkflowRun, WorkflowRunStatus, WorkflowStep
from ..priority_manager.models import TaskPriorityOverride
from ..realtime_bus.bus import publish_event_nowait
from ..workflow_engine.router import get_task_client
from ..workflow_engine.vendor_task_client import AutoXingTaskClient


router = APIRouter(prefix="/controls", tags=["controls"])
logger = logging.getLogger("controls")


@router.post("/tasks/{task_id}/cancel", dependencies=[Depends(require_role("operator"))])
def cancel_task(task_id: int, reason: Optional[str] = None, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in (TaskStatus.DONE, TaskStatus.CANCELED):
        return {"ok": True, "note": f"Task already {task.status}"}

    task.status = TaskStatus.CANCELED
    if reason:
        task.notes = (task.notes or "") + f"\n[CANCELED] {reason}"

    session.add(task)
    session.commit()
    logger.info("task.canceled id=%s reason=%s", task_id, reason)

    publish_event_nowait("task.canceled", {"task_id": task_id, "reason": reason}, source="controls")
    publish_event_nowait("system.updated", {"reason": "task.canceled"}, source="controls")

    return {"ok": True, "task_id": task_id}


@router.post("/runs/{run_id}/cancel", dependencies=[Depends(require_role("operator"))])
def cancel_workflow_run(run_id: int, reason: Optional[str] = None, session: Session = Depends(get_session)):
    run = session.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="WorkflowRun not found")

    if run.status in (WorkflowRunStatus.DONE, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELED):
        return {"ok": True, "note": f"Run already {run.status}"}

    run.status = WorkflowRunStatus.CANCELED
    if reason:
        run.last_error = (run.last_error or "") + f"\n[CANCELED] {reason}"

    session.add(run)

    # also cancel underlying task so it doesn't get re-assigned
    task = session.get(Task, run.task_id)
    if task and task.status not in (TaskStatus.DONE, TaskStatus.CANCELED):
        task.status = TaskStatus.CANCELED
        if reason:
            task.notes = (task.notes or "") + f"\n[CANCELED] {reason}"
        session.add(task)

    session.commit()
    logger.info("workflow.canceled run_id=%s task_id=%s reason=%s", run_id, run.task_id, reason)

    publish_event_nowait(
        "workflow.canceled",
        {"run_id": run_id, "task_id": run.task_id, "robot_id": run.robot_id, "reason": reason},
        source="controls",
    )
    publish_event_nowait("system.updated", {"reason": "workflow.canceled"}, source="controls")

    return {"ok": True, "run_id": run_id, "task_id": run.task_id, "robot_id": run.robot_id}


@router.post("/vendor-task/{vendor_task_id}/cancel", dependencies=[Depends(require_role("admin"))])
async def cancel_vendor_task(vendor_task_id: str, task_client: AutoXingTaskClient = Depends(get_task_client)):
    """
    Placeholder until you add vendor cancel into AutoXingTaskClient.
    """
    if hasattr(task_client, "task_cancel"):
        resp = await task_client.task_cancel(vendor_task_id)
        ok = bool(resp.get("ok")) if isinstance(resp, dict) else False
        if not ok and isinstance(resp, dict) and resp.get("status") == 200:
            ok = True
        return {"ok": ok, "vendor_response": resp, "vendor_task_id": vendor_task_id}

    return {"ok": False, "note": "Vendor cancel not available on task client", "vendor_task_id": vendor_task_id}


@router.post("/reset", dependencies=[Depends(require_role("admin"))])
def reset_system(session: Session = Depends(get_session)):
    """
    Admin-only reset: clear tasks, workflow runs/steps, and priority overrides.
    """
    deleted = {}
    for model, name in (
        (WorkflowStep, "workflow_steps"),
        (WorkflowRun, "workflow_runs"),
        (TaskPriorityOverride, "task_priority_overrides"),
        (Task, "tasks"),
    ):
        result = session.exec(delete(model))
        deleted[name] = result.rowcount

    session.commit()
    logger.info("system.reset deleted=%s", deleted)
    publish_event_nowait("system.reset", {"deleted": deleted}, source="controls")
    return {"ok": True, "deleted": deleted}
