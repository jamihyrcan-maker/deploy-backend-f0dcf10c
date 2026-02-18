from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class PoiMappingUpsertRequest(BaseModel):
    kind: str = Field(..., examples=["TABLE", "KITCHEN", "OPERATOR", "WASHING"])
    ref: str = Field(..., examples=["12", "main"])
    poi_id: str
    area_id: Optional[str] = None
    label: Optional[str] = None


class PoiMappingRead(BaseModel):
    kind: str
    ref: str
    poi_id: str
    area_id: Optional[str] = None
    label: Optional[str] = None


class AutoMapRequest(BaseModel):
    robot_id: str
    table_count: int = 20
    ref_prefix: str = ""  # e.g. "T" if your refs are "T12"
