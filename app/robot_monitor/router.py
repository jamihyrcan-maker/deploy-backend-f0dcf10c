from __future__ import annotations

from fastapi import APIRouter, Depends

from .cache import cache
from ..auth_roles.deps import require_role

router = APIRouter(prefix="/robot-monitor", tags=["robot-monitor"])


@router.get("/states", dependencies=[Depends(require_role("monitor"))])
async def states():
    return await cache.all()
