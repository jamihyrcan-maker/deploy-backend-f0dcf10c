from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from ..auth_roles.deps import require_role
from .models import POI, RobotState
from .service import RobotAPIService

router = APIRouter(prefix="/robot-api", tags=["robot-api"])


def get_robot_api_service() -> RobotAPIService:
    # Overridden in app/main.py
    raise RuntimeError("RobotAPIService dependency not configured")


@router.get("/robots/{robot_id}/state", response_model=RobotState, dependencies=[Depends(require_role("monitor"))])
async def robot_state(robot_id: str, svc: RobotAPIService = Depends(get_robot_api_service)):
    return await svc.get_robot_state(robot_id)


@router.get("/robots/{robot_id}/pois", response_model=List[POI], dependencies=[Depends(require_role("monitor"))])
async def robot_pois(
    robot_id: str,
    only_current_area: bool = True,
    svc: RobotAPIService = Depends(get_robot_api_service),
):
    return await svc.list_pois(robot_id, only_current_area=only_current_area)
