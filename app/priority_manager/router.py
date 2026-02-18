from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..persistence.db import get_session
from ..realtime_bus.bus import publish_event_nowait
from ..auth_roles.deps import require_role

from .schemas import SetOverrideRequest, SetOverrideResponse, ClearOverrideResponse
from .service import PriorityService

router = APIRouter(prefix="/priority", tags=["priority-manager"])


@router.post("/override", response_model=SetOverrideResponse, dependencies=[Depends(require_role("operator"))])
def set_override(payload: SetOverrideRequest, session: Session = Depends(get_session)):
    row = PriorityService.set_override(session, payload.task_id, payload.override)

    publish_event_nowait("priority.override_set", {
        "task_id": row.task_id,
        "override": row.override,
        "reason": payload.reason,
    }, source="priority-manager")

    return SetOverrideResponse(ok=True, task_id=row.task_id, override=row.override)


@router.delete("/override/{task_id}", response_model=ClearOverrideResponse, dependencies=[Depends(require_role("operator"))])
def clear_override(task_id: int, session: Session = Depends(get_session)):
    ok = PriorityService.clear_override(session, task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Override not found")

    publish_event_nowait("priority.override_cleared", {"task_id": task_id}, source="priority-manager")
    return ClearOverrideResponse(ok=True, task_id=task_id)
