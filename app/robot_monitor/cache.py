from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RobotStateCache:
    """
    In-memory cache of latest robot state snapshots.
    Structure: robot_id -> (timestamp_iso, state_dict)
    """
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._data: Dict[str, Tuple[str, Dict[str, Any]]] = {}

    async def set(self, robot_id: str, state: Dict[str, Any]) -> None:
        async with self._lock:
            self._data[robot_id] = (utc_now_iso(), state)

    async def get(self, robot_id: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        async with self._lock:
            return self._data.get(robot_id)

    async def all(self) -> Dict[str, Dict[str, Any]]:
        async with self._lock:
            return {
                rid: {"ts": ts, "state": st}
                for rid, (ts, st) in self._data.items()
            }


# Global singleton cache
cache = RobotStateCache()
