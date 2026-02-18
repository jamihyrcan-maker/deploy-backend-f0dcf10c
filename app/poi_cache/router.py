from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..persistence.db import get_session
from ..auth_roles.deps import require_role
from .service import PoiCacheService


router = APIRouter(prefix="/poi-cache", tags=["poi-cache"])


@router.get("/pois", dependencies=[Depends(require_role("monitor"))])
def list_cached_pois(robot_id: Optional[str] = None, limit: int = 200, offset: int = 0, session: Session = Depends(get_session)):
    svc = PoiCacheService(session)
    return svc.list_pois(robot_id=robot_id, limit=limit, offset=offset)
