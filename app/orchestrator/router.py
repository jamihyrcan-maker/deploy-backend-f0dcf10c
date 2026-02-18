from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..assignment_engine.service import AssignmentEngineService
from ..auth_roles.deps import require_role
from ..persistence.db import get_session
from ..queue_manager.service import QueueManagerService
from ..realtime_bus.bus import publish_event_nowait
from ..robot_api.router import get_robot_api_service
from ..robot_api.service import RobotAPIService
from ..workflow_engine.service import WorkflowEngineService
from ..workflow_engine.router import get_task_client
from ..workflow_engine.vendor_task_client import AutoXingTaskClient

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.post("/tick", dependencies=[Depends(require_role("operator"))])
async def tick(
    max_assignments: int = 5,
    preferred_robot_id: Optional[str] = None,
    session: Session = Depends(get_session),
    robot_api: RobotAPIService = Depends(get_robot_api_service),
    task_client: AutoXingTaskClient = Depends(get_task_client),
):
    qm = QueueManagerService(session)
    promoted = qm.tick_promote_due_tasks()

    ae = AssignmentEngineService(session, robot_api, task_client)
    assigned = 0
    for _ in range(max(0, int(max_assignments))):
        res = await ae.assign_next(preferred_robot_id=preferred_robot_id, include_robot_state=False)
        if not res.get("assigned"):
            break
        assigned += 1

    wf = WorkflowEngineService(session, robot_api, task_client)
    wf_tick = await wf.tick()

    payload = {
        "promoted": promoted,
        "assigned": assigned,
        "workflow": wf_tick,
    }

    publish_event_nowait("orchestrator.ticked", payload, source="orchestrator")
    if promoted or assigned or wf_tick.get("progressed_runs") or wf_tick.get("finished_runs") or wf_tick.get("failed_runs"):
        publish_event_nowait("system.updated", {"reason": "orchestrator.tick"}, source="orchestrator")

    return payload
