from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PoiMapping(SQLModel, table=True):
    """
    Explicit mapping from (target_kind, target_ref) -> vendor poi_id (and optional area_id).
    Examples:
      - kind="TABLE", ref="12"  => poi_id="xxxx"
      - kind="KITCHEN", ref="main" => poi_id="yyyy"
      - kind="OPERATOR", ref="main" => poi_id="zzzz"
      - kind="WASHING", ref="main" => poi_id="aaaa"
    """
    kind: str = Field(primary_key=True)
    ref: str = Field(primary_key=True)

    poi_id: str = Field(index=True)
    area_id: Optional[str] = Field(default=None, index=True)

    label: Optional[str] = None
    updated_at: datetime = Field(default_factory=utc_now, index=True)
