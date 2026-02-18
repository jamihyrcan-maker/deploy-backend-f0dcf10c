from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field as PydField

from ..persistence.models import WorkflowRunStatus, WorkflowStepType


class StartWorkflowRequest(BaseModel):
    task_id: int
    robot_id: str = PydField(..., min_length=1)


class StartWorkflowResponse(BaseModel):
    run_id: int
    status: WorkflowRunStatus
    total_steps: int
    current_step_index: int


class TickResponse(BaseModel):
    progressed_runs: int
    finished_runs: int
    failed_runs: int


class ConfirmStepRequest(BaseModel):
    decision: str = PydField(..., min_length=1)  # e.g. YES/NO/COMPLETED/POSTPONE
    payload: Optional[Dict[str, Any]] = None     # extra data


class WorkflowStepRead(BaseModel):
    id: int
    step_index: int
    step_type: WorkflowStepType
    step_code: str

    area_id: Optional[str]
    x: Optional[float]
    y: Optional[float]
    yaw: Optional[float]
    stop_radius: float

    wait_seconds: Optional[int]
    completed_at: Optional[datetime]
    decision: Optional[str]
    label: Optional[str]


class WorkflowRunRead(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime

    task_id: int
    robot_id: str
    status: WorkflowRunStatus

    current_step_index: int
    total_steps: int

    current_vendor_task_id: Optional[str]
    last_error: Optional[str]


class WorkflowRunDetail(BaseModel):
    run: WorkflowRunRead
    steps: List[WorkflowStepRead]
