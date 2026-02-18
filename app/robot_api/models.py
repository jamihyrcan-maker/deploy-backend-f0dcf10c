from __future__ import annotations
from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class RobotState(BaseModel):
    robotId: str
    battery: Optional[float] = None
    isOnline: Optional[bool] = None
    isCharging: Optional[bool] = None
    isEmergencyStop: Optional[bool] = None
    isManualMode: Optional[bool] = None
    moveState: Optional[Any] = None
    areaId: Optional[str] = None
    businessId: Optional[str] = None

    # Keep full vendor payload for forward compatibility
    raw: Dict[str, Any]


class POI(BaseModel):
    id: str
    name: Optional[str] = None
    areaId: Optional[str] = None
    coordinate: Optional[List[float]] = None  # [x, y]
    yaw: Optional[float] = None

    raw: Dict[str, Any]
