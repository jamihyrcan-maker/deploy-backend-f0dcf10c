from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..persistence.db import get_session
from ..realtime_bus.bus import publish_event_nowait
from ..auth_roles.deps import require_role
from .service import QueueManagerService

router = APIRouter(prefix="/queue-manager", tags=["queue-manager"])


@router.post("/tick", dependencies=[Depends(require_role("operator"))])
def tick(session: Session = Depends(get_session)):
    svc = QueueManagerService(session)
    promoted = svc.tick_promote_due_tasks()

    publish_event_nowait("queue.ticked", {"promoted": promoted}, source="queue-manager")
    if promoted:
        publish_event_nowait("queue.updated", {"reason": "promoted_due_tasks"}, source="queue-manager")

    return {"promoted": promoted}


@router.get("/queue", dependencies=[Depends(require_role("monitor"))])
def queue(session: Session = Depends(get_session)):
    svc = QueueManagerService(session)
    return {"queue": svc.get_ready_queue()}


@router.get("/stats", dependencies=[Depends(require_role("monitor"))])
def stats(session: Session = Depends(get_session)):
    svc = QueueManagerService(session)
    return svc.stats()
