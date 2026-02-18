from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    DONE = "DONE"
    CANCELED = "CANCELED"


class TaskType(str, Enum):
    ORDERING = "ORDERING"
    DELIVERY = "DELIVERY"
    CLEANUP = "CLEANUP"
    BILLING = "BILLING"
    NAVIGATE = "NAVIGATE"
    CHARGING = "CHARGING"


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)

    status: TaskStatus = Field(default=TaskStatus.READY, index=True)
    task_type: TaskType = Field(default=TaskType.NAVIGATE, index=True)

    title: str = Field(index=True)
    notes: Optional[str] = None

    # Target definition (still generic)
    target_kind: str = Field(default="POI")
    target_ref: str = Field(default="")

    # Scheduling: operator chooses instant vs delayed
    release_at: Optional[datetime] = Field(default=None, index=True)

    assigned_robot_id: Optional[str] = Field(default=None, index=True)

    created_by: Optional[str] = Field(default="operator")


class RobotPOICache(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("robot_id", "poi_id", name="uix_robot_poi"),)

    id: Optional[int] = Field(default=None, primary_key=True)

    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)

    robot_id: str = Field(index=True)
    poi_id: str = Field(index=True)

    name: Optional[str] = Field(default=None, index=True)
    area_id: Optional[str] = Field(default=None, index=True)

    x: Optional[float] = None
    y: Optional[float] = None
    yaw: Optional[float] = None

    raw_json: Optional[str] = None


# ----------------------------
# Workflow / Execution persistence
# ----------------------------
class WorkflowRunStatus(str, Enum):
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class WorkflowStepType(str, Enum):
    NAVIGATE = "NAVIGATE"
    WAIT = "WAIT"
    MANUAL_CONFIRM = "MANUAL_CONFIRM"


class WorkflowRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)

    task_id: int = Field(index=True)
    robot_id: str = Field(index=True)

    status: WorkflowRunStatus = Field(default=WorkflowRunStatus.RUNNING, index=True)

    current_step_index: int = Field(default=0)
    total_steps: int = Field(default=0)

    current_vendor_task_id: Optional[str] = Field(default=None, index=True)
    last_error: Optional[str] = None


class WorkflowStep(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    run_id: int = Field(index=True)
    step_index: int = Field(index=True)

    step_type: WorkflowStepType = Field(index=True)

    # A stable "meaning" for manual steps (e.g., DELIVERY_LOADED, ORDER_DECISION, CLEANUP_HAS_DISHES)
    step_code: str = Field(default="", index=True)

    # For NAVIGATE steps (resolved target)
    area_id: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    yaw: Optional[float] = None
    stop_radius: float = 1.0

    # For WAIT steps
    wait_seconds: Optional[int] = None

    # For MANUAL_CONFIRM steps
    completed_at: Optional[datetime] = Field(default=None, index=True)
    decision: Optional[str] = None
    decision_payload: Optional[str] = None  # JSON string (simple v0 storage)

    label: Optional[str] = None
