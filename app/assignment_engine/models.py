from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

class RobotInfo(BaseModel):
    robot_id: str
    busy: bool
    eligible: bool
    reason: Optional[str] = None
    state: Optional[Dict[str, Any]] = None


class RobotsResponse(BaseModel):
    robots: List[RobotInfo]


class AssignNextRequest(BaseModel):
    preferred_robot_id: Optional[str] = None
    include_robot_state: bool = False


class AssignNextResponse(BaseModel):
    assigned: bool
    task_id: Optional[int] = None
    robot_id: Optional[str] = None
    run_id: Optional[int] = None
    message: Optional[str] = None


class UnassignRequest(BaseModel):
    task_id: int
    reason: Optional[str] = None


class UnassignResponse(BaseModel):
    ok: bool
    message: str


class AssignmentsResponse(BaseModel):
    assigned_tasks: List[Dict[str, Any]]
    running_workflows: List[Dict[str, Any]]
