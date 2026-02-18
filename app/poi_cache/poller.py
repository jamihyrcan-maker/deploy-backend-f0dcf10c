import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from sqlmodel import Session

from ..persistence.db import engine
from ..robot_api.service import RobotAPIService
from ..realtime_bus.bus import publish_event
from .service import PoiCacheService


logger = logging.getLogger("poi-cache")


def _to_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, dict):
        return obj
    return {"value": str(obj)}


def _stable_hash(items: List[Dict[str, Any]]) -> str:
    payload = sorted(items, key=lambda x: str(x.get("id", "")))
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class PoiCachePoller:
    """
    Polls vendor POIs periodically and stores them in DB.
    Updates only when changes are detected.
    """
    def __init__(self, robot_api: RobotAPIService, robot_ids: List[str], interval_s: float = 7200.0) -> None:
        self.robot_api = robot_api
        self.robot_ids = [r for r in robot_ids if r]
        self.interval_s = max(60.0, float(interval_s))
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._last_hash: Dict[str, str] = {}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("POI cache poller started interval=%.0fs", self.interval_s)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except Exception:
                pass

    async def _loop(self) -> None:
        await asyncio.sleep(1.0)
        while not self._stop.is_set():
            for rid in self.robot_ids:
                try:
                    pois = await self.robot_api.list_pois(rid, only_current_area=False)
                    poi_dicts = [_to_dict(p) for p in pois]
                    h = _stable_hash(poi_dicts)
                    if self._last_hash.get(rid) == h:
                        continue

                    with Session(engine) as session:
                        svc = PoiCacheService(session)
                        result = svc.update_robot_pois(rid, poi_dicts)

                    self._last_hash[rid] = h
                    await publish_event(
                        "poi.cache_updated",
                        {"robot_id": rid, **result},
                        source="poi-cache",
                    )
                except Exception as e:
                    logger.warning("POI cache error for %s: %s", rid, e)
                    await publish_event(
                        "poi.cache_error",
                        {"robot_id": rid, "error": str(e)},
                        source="poi-cache",
                    )

                await asyncio.sleep(0.1)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                pass
