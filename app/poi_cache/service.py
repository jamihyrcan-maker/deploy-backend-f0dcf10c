import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import Session, select

from ..persistence.models import RobotPOICache


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_json(d: Dict[str, Any]) -> str:
    return json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _poi_fields(poi: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[str], Optional[float], Optional[float], Optional[float], str]:
    poi_id = str(poi.get("id", "")).strip()
    name = poi.get("name")
    area_id = poi.get("areaId") or poi.get("area_id")
    coord = poi.get("coordinate") or []
    x = float(coord[0]) if isinstance(coord, (list, tuple)) and len(coord) > 0 else None
    y = float(coord[1]) if isinstance(coord, (list, tuple)) and len(coord) > 1 else None
    yaw = poi.get("yaw")
    raw = poi.get("raw") if isinstance(poi.get("raw"), dict) else poi
    raw_json = _stable_json(raw if isinstance(raw, dict) else {"raw": raw})
    return poi_id, name, area_id, x, y, yaw, raw_json


class PoiCacheService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_pois(self, robot_id: Optional[str] = None, limit: int = 200, offset: int = 0) -> List[RobotPOICache]:
        stmt = select(RobotPOICache)
        if robot_id:
            stmt = stmt.where(RobotPOICache.robot_id == robot_id)
        stmt = stmt.order_by(RobotPOICache.updated_at.desc()).offset(offset).limit(limit)
        return list(self.session.exec(stmt).all())

    def update_robot_pois(self, robot_id: str, pois: List[Dict[str, Any]]) -> Dict[str, int]:
        now = utc_now()
        incoming: Dict[str, Dict[str, Any]] = {}
        for poi in pois:
            if not isinstance(poi, dict):
                continue
            poi_id, name, area_id, x, y, yaw, raw_json = _poi_fields(poi)
            if not poi_id:
                continue
            incoming[poi_id] = {
                "poi_id": poi_id,
                "name": name,
                "area_id": area_id,
                "x": x,
                "y": y,
                "yaw": yaw,
                "raw_json": raw_json,
            }

        existing = list(self.session.exec(select(RobotPOICache).where(RobotPOICache.robot_id == robot_id)).all())
        existing_by_id = {e.poi_id: e for e in existing}

        created = 0
        updated = 0
        deleted = 0

        # delete removed
        for e in existing:
            if e.poi_id not in incoming:
                self.session.delete(e)
                deleted += 1

        # upsert incoming
        for poi_id, data in incoming.items():
            e = existing_by_id.get(poi_id)
            if e is None:
                e = RobotPOICache(
                    robot_id=robot_id,
                    poi_id=poi_id,
                    name=data["name"],
                    area_id=data["area_id"],
                    x=data["x"],
                    y=data["y"],
                    yaw=data["yaw"],
                    raw_json=data["raw_json"],
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(e)
                created += 1
                continue

            changed = (
                e.name != data["name"]
                or e.area_id != data["area_id"]
                or e.x != data["x"]
                or e.y != data["y"]
                or e.yaw != data["yaw"]
                or e.raw_json != data["raw_json"]
            )
            if changed:
                e.name = data["name"]
                e.area_id = data["area_id"]
                e.x = data["x"]
                e.y = data["y"]
                e.yaw = data["yaw"]
                e.raw_json = data["raw_json"]
                e.updated_at = now
                self.session.add(e)
                updated += 1

        if created or updated or deleted:
            self.session.commit()

        return {
            "created": created,
            "updated": updated,
            "deleted": deleted,
            "total": len(incoming),
        }
