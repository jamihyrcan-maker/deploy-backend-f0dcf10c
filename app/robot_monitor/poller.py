from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from ..robot_api.service import RobotAPIService
from ..realtime_bus.bus import publish_event
from .cache import cache


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


def _stable_hash(d: Dict[str, Any]) -> str:
    # stable hash for change detection
    return json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class RobotStatePoller:
    """
    Polls robot state periodically and:
      - stores last state in cache
      - broadcasts robot.state_updated over WS when state changes
    """
    def __init__(self, robot_api: RobotAPIService, robot_ids: List[str], interval_s: float = 5.0) -> None:
        self.robot_api = robot_api
        self.robot_ids = [r for r in robot_ids if r]
        self.interval_s = max(1.0, float(interval_s))
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._last_hash: Dict[str, str] = {}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except Exception:
                pass

    async def _loop(self) -> None:
        # small startup delay so app fully boots
        await asyncio.sleep(0.5)

        while not self._stop.is_set():
            for rid in self.robot_ids:
                try:
                    state_obj = await self.robot_api.get_state(rid)
                    state = _to_dict(state_obj)

                    await cache.set(rid, state)

                    h = _stable_hash(state)
                    if self._last_hash.get(rid) != h:
                        self._last_hash[rid] = h
                        await publish_event(
                            "robot.state_updated",
                            {"robot_id": rid, "state": state},
                            source="robot-monitor",
                        )
                except Exception as e:
                    # still publish errors sometimes, useful for UI
                    await publish_event(
                        "robot.state_error",
                        {"robot_id": rid, "error": str(e)},
                        source="robot-monitor",
                    )

                # avoid hammering vendor if many robots
                await asyncio.sleep(0.1)

            # wait next cycle
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                pass
