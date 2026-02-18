from __future__ import annotations

import asyncio
import os
import logging
from typing import Optional

import httpx


log = logging.getLogger("auto-tick")


class AutoTickRunner:
    """
    Optional background loop that periodically calls:
      POST /orchestrator/tick

    Disabled by default. Enable with:
      AUTO_TICK_ENABLED=1

    Required:
      AUTO_TICK_API_KEY must be operator/admin key.
    """
    def __init__(self) -> None:
        self.enabled = os.getenv("AUTO_TICK_ENABLED", "0") == "1"
        self.interval_s = float(os.getenv("AUTO_TICK_INTERVAL_S", "2.0"))
        self.url = os.getenv("AUTO_TICK_URL", "http://127.0.0.1:8000/orchestrator/tick")
        self.api_key = os.getenv("AUTO_TICK_API_KEY", "dev-operator-key")
        self.max_assignments = int(os.getenv("AUTO_TICK_MAX_ASSIGNMENTS", "2"))

        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if not self.enabled:
            log.info("AUTO_TICK disabled")
            return
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        log.info("AUTO_TICK enabled interval=%.2fs url=%s", self.interval_s, self.url)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except Exception:
                pass

    async def _loop(self) -> None:
        await asyncio.sleep(1.0)  # let server finish startup

        async with httpx.AsyncClient(timeout=10.0) as client:
            while not self._stop.is_set():
                try:
                    r = await client.post(
                        self.url,
                        params={"max_assignments": self.max_assignments},
                        headers={"X-API-Key": self.api_key},
                    )
                    if r.status_code >= 400:
                        log.warning("tick failed status=%s body=%s", r.status_code, r.text[:200])
                    else:
                        log.debug("tick ok: %s", r.text[:200])
                except Exception as e:
                    log.warning("tick exception: %s", e)

                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
                except asyncio.TimeoutError:
                    pass
