from __future__ import annotations
from typing import List

from .autox_client import AutoXingClient
from .models import RobotState, POI


class RobotAPIService:
    """
    STANDARD interface other backend blocks should depend on.
    Queue Manager / Task Manager / Monitor should call this service,
    not the vendor HTTP layer directly.
    """

    def __init__(self, vendor: AutoXingClient):
        self.vendor = vendor

    async def get_robot_state(self, robot_id: str) -> RobotState:
        data = await self.vendor.robot_state(robot_id)
        return RobotState(
            robotId=robot_id,
            battery=data.get("battery"),
            isOnline=data.get("isOnline"),
            isCharging=data.get("isCharging"),
            isEmergencyStop=data.get("isEmergencyStop"),
            isManualMode=data.get("isManualMode"),
            moveState=data.get("moveState"),
            areaId=data.get("areaId"),
            businessId=data.get("businessId"),
            raw=data,
        )

    async def get_state(self, robot_id: str) -> RobotState:
        # Backward-compatible alias
        return await self.get_robot_state(robot_id)

    async def list_pois(self, robot_id: str, only_current_area: bool = True) -> List[POI]:
        state = await self.get_robot_state(robot_id)
        pois = await self.vendor.poi_list(robot_id)

        if only_current_area and state.areaId:
            pois = [p for p in pois if p.get("areaId") == state.areaId]

        out: List[POI] = []
        for p in pois:
            out.append(
                POI(
                    id=p["id"],
                    name=p.get("name"),
                    areaId=p.get("areaId"),
                    coordinate=p.get("coordinate"),
                    yaw=p.get("yaw"),
                    raw=p,
                )
            )
        return out
