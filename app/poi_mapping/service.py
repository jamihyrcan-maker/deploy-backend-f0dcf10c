from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from .models import PoiMapping
from ..robot_api.service import RobotAPIService


class PoiMappingService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def norm_kind(kind: str) -> str:
        return (kind or "").strip().upper()

    @staticmethod
    def norm_ref(ref: str) -> str:
        return (ref or "").strip()

    def upsert(self, kind: str, ref: str, poi_id: str, area_id: Optional[str], label: Optional[str]) -> PoiMapping:
        k = self.norm_kind(kind)
        r = self.norm_ref(ref)

        row = self.session.get(PoiMapping, (k, r))
        if row is None:
            row = PoiMapping(kind=k, ref=r, poi_id=poi_id, area_id=area_id, label=label)
        else:
            row.poi_id = poi_id
            row.area_id = area_id
            row.label = label or row.label

        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete(self, kind: str, ref: str) -> bool:
        k = self.norm_kind(kind)
        r = self.norm_ref(ref)
        row = self.session.get(PoiMapping, (k, r))
        if row is None:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def list_all(self) -> List[PoiMapping]:
        stmt = select(PoiMapping).order_by(PoiMapping.kind.asc(), PoiMapping.ref.asc())
        return list(self.session.exec(stmt).all())

    def get(self, kind: str, ref: str) -> Optional[PoiMapping]:
        k = self.norm_kind(kind)
        r = self.norm_ref(ref)
        return self.session.get(PoiMapping, (k, r))

    # ----------------------------
    # Auto-mapping helper (best-effort)
    # ----------------------------
    async def auto_map_from_pois(self, robot_api: RobotAPIService, robot_id: str, table_count: int, ref_prefix: str = "") -> Dict[str, int]:
        """
        Best-effort auto-map using POI names:
          - maps tables 1..table_count using number matching
          - maps kitchen/operator/washing by keyword
        You can still override manually with /poi-mapping/mappings.
        """
        pois = await robot_api.list_pois(robot_id, only_current_area=False)

        def norm(s: str) -> str:
            return re.sub(r"\s+", " ", (s or "").strip().lower())

        # Build an index for quick search
        by_id = {p.id: p for p in pois}
        name_list: List[Tuple[str, str]] = [(p.id, norm(p.name or "")) for p in pois]

        created = 0
        updated = 0

        # Map special locations
        def find_first_keyword(keywords: List[str]) -> Optional[str]:
            for pid, nm in name_list:
                for kw in keywords:
                    if kw in nm:
                        return pid
            return None

        kitchen_id = find_first_keyword(["kitchen"])
        operator_id = find_first_keyword(["operator"])
        washing_id = find_first_keyword(["wash", "dish", "sink"])

        if kitchen_id:
            p = by_id[kitchen_id]
            self.upsert("KITCHEN", "main", kitchen_id, getattr(p, "areaId", None), "Kitchen")
            updated += 1
        if operator_id:
            p = by_id[operator_id]
            self.upsert("OPERATOR", "main", operator_id, getattr(p, "areaId", None), "Operator")
            updated += 1
        if washing_id:
            p = by_id[washing_id]
            self.upsert("WASHING", "main", washing_id, getattr(p, "areaId", None), "Washing/Dish Area")
            updated += 1

        # Map tables
        for n in range(1, max(1, table_count) + 1):
            ref = f"{ref_prefix}{n}".strip()
            chosen: Optional[str] = None

            # prefer entries containing "table" + number
            for pid, nm in name_list:
                if ("table" in nm or "tbl" in nm) and str(n) in nm:
                    chosen = pid
                    break

            # fallback: any POI containing number
            if not chosen:
                for pid, nm in name_list:
                    if str(n) in nm:
                        chosen = pid
                        break

            if chosen:
                p = by_id[chosen]
                self.upsert("TABLE", str(n), chosen, getattr(p, "areaId", None), f"Table {n}")
                updated += 1

        return {"updated": updated, "created": created}
