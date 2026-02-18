from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth_roles.deps import require_role
from ..persistence.db import get_session
from ..persistence.models import WorkflowRun, WorkflowStep, WorkflowStepType
from ..realtime_bus.bus import publish_event_nowait
from ..robot_api.router import get_robot_api_service
from ..robot_api.service import RobotAPIService
from .models import (
    ConfirmStepRequest,
    StartWorkflowRequest,
    StartWorkflowResponse,
    TickResponse,
    WorkflowRunDetail,
    WorkflowRunRead,
    WorkflowStepRead,
)
from .service import WorkflowEngineService
from .vendor_task_client import AutoXingTaskClient

router = APIRouter(prefix="/workflow-engine", tags=["workflow-engine"])


def get_task_client() -> AutoXingTaskClient:
    raise RuntimeError("Task client dependency not configured (main.py should override)")


def get_workflow_service(
    session: Session = Depends(get_session),
    robot_api: RobotAPIService = Depends(get_robot_api_service),
    task_client: AutoXingTaskClient = Depends(get_task_client),
) -> WorkflowEngineService:
    return WorkflowEngineService(session, robot_api, task_client)


@router.post("/runs", response_model=StartWorkflowResponse, dependencies=[Depends(require_role("operator"))])
async def start_run(payload: StartWorkflowRequest, svc: WorkflowEngineService = Depends(get_workflow_service)):
    try:
        run = await svc.start_run(payload.task_id, payload.robot_id)

        publish_event_nowait("workflow.run_started", {
            "run_id": run.id,
            "task_id": run.task_id,
            "robot_id": run.robot_id,
            "total_steps": run.total_steps,
            "current_step_index": run.current_step_index,
        }, source="workflow-engine")

        # If first step is manual, notify UI
        steps = svc.get_steps(run.id)
        cur = next((s for s in steps if s.step_index == run.current_step_index), None)
        if cur and cur.step_type == WorkflowStepType.MANUAL_CONFIRM:
            publish_event_nowait("workflow.needs_confirm", {
                "run_id": run.id,
                "task_id": run.task_id,
                "robot_id": run.robot_id,
                "step_index": cur.step_index,
                "step_code": cur.step_code,
                "label": cur.label,
            }, source="workflow-engine")

        return StartWorkflowResponse(
            run_id=run.id,
            status=run.status,
            total_steps=run.total_steps,
            current_step_index=run.current_step_index,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tick", response_model=TickResponse, dependencies=[Depends(require_role("operator"))])
async def tick(svc: WorkflowEngineService = Depends(get_workflow_service)):
    res = await svc.tick()

    publish_event_nowait("workflow.ticked", res, source="workflow-engine")
    if res.get("progressed_runs") or res.get("finished_runs") or res.get("failed_runs"):
        publish_event_nowait("workflow.updated", {"reason": "tick"}, source="workflow-engine")

    return TickResponse(**res)


@router.post("/runs/{run_id}/confirm", response_model=WorkflowRunRead, dependencies=[Depends(require_role("operator"))])
async def confirm(run_id: int, payload: ConfirmStepRequest, svc: WorkflowEngineService = Depends(get_workflow_service)):
    try:
        run = await svc.confirm_current_step(run_id, payload.decision, payload.payload)

        publish_event_nowait("workflow.confirmed", {
            "run_id": run.id,
            "task_id": run.task_id,
            "robot_id": run.robot_id,
            "decision": payload.decision,
        }, source="workflow-engine")

        # After confirm, check if next step needs confirm too
        steps = svc.get_steps(run.id)
        cur = next((s for s in steps if s.step_index == run.current_step_index), None)
        if cur and cur.step_type == WorkflowStepType.MANUAL_CONFIRM:
            publish_event_nowait("workflow.needs_confirm", {
                "run_id": run.id,
                "task_id": run.task_id,
                "robot_id": run.robot_id,
                "step_index": cur.step_index,
                "step_code": cur.step_code,
                "label": cur.label,
            }, source="workflow-engine")

        return WorkflowRunRead(
            id=run.id,
            created_at=run.created_at,
            updated_at=run.updated_at,
            task_id=run.task_id,
            robot_id=run.robot_id,
            status=run.status,
            current_step_index=run.current_step_index,
            total_steps=run.total_steps,
            current_vendor_task_id=run.current_vendor_task_id,
            last_error=run.last_error,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs", response_model=list[WorkflowRunRead], dependencies=[Depends(require_role("monitor"))])
def list_runs(limit: int = 50, offset: int = 0, svc: WorkflowEngineService = Depends(get_workflow_service)):
    stmt = select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit)
    runs = list(svc.session.exec(stmt).all())
    return [
        WorkflowRunRead(
            id=r.id,
            created_at=r.created_at,
            updated_at=r.updated_at,
            task_id=r.task_id,
            robot_id=r.robot_id,
            status=r.status,
            current_step_index=r.current_step_index,
            total_steps=r.total_steps,
            current_vendor_task_id=r.current_vendor_task_id,
            last_error=r.last_error,
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=WorkflowRunDetail, dependencies=[Depends(require_role("monitor"))])
def run_detail(run_id: int, svc: WorkflowEngineService = Depends(get_workflow_service)):
    run = svc.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = svc.get_steps(run_id)

    return WorkflowRunDetail(
        run=WorkflowRunRead(
            id=run.id,
            created_at=run.created_at,
            updated_at=run.updated_at,
            task_id=run.task_id,
            robot_id=run.robot_id,
            status=run.status,
            current_step_index=run.current_step_index,
            total_steps=run.total_steps,
            current_vendor_task_id=run.current_vendor_task_id,
            last_error=run.last_error,
        ),
        steps=[
            WorkflowStepRead(
                id=s.id,
                step_index=s.step_index,
                step_type=s.step_type,
                step_code=s.step_code,
                area_id=s.area_id,
                x=s.x,
                y=s.y,
                yaw=s.yaw,
                stop_radius=s.stop_radius,
                wait_seconds=s.wait_seconds,
                completed_at=s.completed_at,
                decision=s.decision,
                label=s.label,
            )
            for s in steps
        ],
    )
