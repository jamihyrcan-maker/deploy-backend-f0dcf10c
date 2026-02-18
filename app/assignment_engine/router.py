from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..auth_roles.deps import require_role
from ..persistence.db import get_session
from ..realtime_bus.bus import publish_event_nowait
from ..robot_api.router import get_robot_api_service
from ..robot_api.service import RobotAPIService
from ..workflow_engine.router import get_task_client
from ..workflow_engine.vendor_task_client import AutoXingTaskClient
from .service import AssignmentEngineService

router = APIRouter(prefix="/assignment", tags=["assignment-engine"])


@router.get("/robots", dependencies=[Depends(require_role("monitor"))])
async def robots(include_state: bool = False, session: Session = Depends(get_session), robot_api: RobotAPIService = Depends(get_robot_api_service), task_client: AutoXingTaskClient = Depends(get_task_client)):
    svc = AssignmentEngineService(session, robot_api, task_client)
    return await svc.list_robots(include_state=include_state)


@router.post("/assign-next", dependencies=[Depends(require_role("operator"))])
async def assign_next(preferred_robot_id: Optional[str] = None, include_robot_state: bool = False, session: Session = Depends(get_session), robot_api: RobotAPIService = Depends(get_robot_api_service), task_client: AutoXingTaskClient = Depends(get_task_client)):
    svc = AssignmentEngineService(session, robot_api, task_client)
    res = await svc.assign_next(preferred_robot_id=preferred_robot_id, include_robot_state=include_robot_state)

    if res.get("assigned"):
        publish_event_nowait("assignment.made", res, source="assignment-engine")
    else:
        publish_event_nowait("assignment.failed", res, source="assignment-engine")

    return res


@router.get("/assignments", dependencies=[Depends(require_role("monitor"))])
def assignments(session: Session = Depends(get_session), robot_api: RobotAPIService = Depends(get_robot_api_service), task_client: AutoXingTaskClient = Depends(get_task_client)):
    svc = AssignmentEngineService(session, robot_api, task_client)
    return svc.get_assignments()


@router.post("/unassign", dependencies=[Depends(require_role("operator"))])
def unassign(task_id: int, reason: Optional[str] = None, session: Session = Depends(get_session), robot_api: RobotAPIService = Depends(get_robot_api_service), task_client: AutoXingTaskClient = Depends(get_task_client)):
    svc = AssignmentEngineService(session, robot_api, task_client)
    ok = svc.unassign(task_id, reason=reason)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot unassign task (not found or not assigned).")

    publish_event_nowait("assignment.unassigned", {"task_id": task_id, "reason": reason}, source="assignment-engine")
    return {"ok": True}
