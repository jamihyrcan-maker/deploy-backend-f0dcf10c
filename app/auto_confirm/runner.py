from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, Tuple, Dict, Any, List

import httpx


log = logging.getLogger("auto-confirm")


class AutoConfirmRunner:
    """
    Optional background loop that auto-confirms MANUAL_CONFIRM steps.

    Enable with:
      AUTO_CONFIRM_ENABLED=1
    """

    def __init__(self) -> None:
        self.enabled = os.getenv("AUTO_CONFIRM_ENABLED", "0") == "1"
        self.interval_s = float(os.getenv("AUTO_CONFIRM_INTERVAL_S", "2.0"))
        self.base_url = os.getenv("AUTO_CONFIRM_URL", "http://127.0.0.1:8000").rstrip("/")
        self.api_key = os.getenv("AUTO_CONFIRM_API_KEY", "dev-admin-key")

        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if not self.enabled:
            log.info("AUTO_CONFIRM disabled")
            return
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        log.info("AUTO_CONFIRM enabled interval=%.2fs url=%s", self.interval_s, self.base_url)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except Exception:
                pass

    def _decision_for(self, step_code: str) -> Tuple[str, Dict[str, Any]]:
        code = (step_code or "").upper()
        if code == "ORDER_DECISION":
            return "COMPLETED", {}
        if code == "CLEANUP_HAS_DISHES":
            return "YES", {}
        if code == "CLEANUP_MORE_DISHES":
            return "NO", {}
        if code.startswith("DELIVERY_"):
            return "CONFIRM", {}
        if code.startswith("BILLING_"):
            return "CONFIRM", {}
        return "CONFIRM", {}

    async def _fetch_runs(self, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
        resp = await client.get(
            f"{self.base_url}/workflow-engine/runs",
            params={"limit": 50},
            headers={"X-API-Key": self.api_key},
        )
        if resp.status_code >= 400:
            return []
        return resp.json()

    async def _fetch_run_detail(self, client: httpx.AsyncClient, run_id: int) -> Optional[Dict[str, Any]]:
        resp = await client.get(
            f"{self.base_url}/workflow-engine/runs/{run_id}",
            headers={"X-API-Key": self.api_key},
        )
        if resp.status_code >= 400:
            return None
        return resp.json()

    async def _confirm(self, client: httpx.AsyncClient, run_id: int, decision: str, payload: Dict[str, Any]) -> None:
        await client.post(
            f"{self.base_url}/workflow-engine/runs/{run_id}/confirm",
            headers={"X-API-Key": self.api_key},
            json={"decision": decision, "payload": payload},
            timeout=10.0,
        )

    async def _loop(self) -> None:
        await asyncio.sleep(1.0)
        async with httpx.AsyncClient(timeout=10.0) as client:
            while not self._stop.is_set():
                try:
                    runs = await self._fetch_runs(client)
                    for run in runs:
                        if not isinstance(run, dict):
                            continue
                        if str(run.get("status")) != "RUNNING":
                            continue
                        run_id = run.get("id")
                        if not run_id:
                            continue
                        detail = await self._fetch_run_detail(client, int(run_id))
                        if not detail:
                            continue
                        run_obj = detail.get("run") or {}
                        steps = detail.get("steps") or []
                        idx = run_obj.get("current_step_index")
                        cur = next((s for s in steps if s.get("step_index") == idx), None)
                        if not cur:
                            continue
                        if str(cur.get("step_type")) != "MANUAL_CONFIRM":
                            continue
                        decision, payload = self._decision_for(cur.get("step_code", ""))
                        await self._confirm(client, int(run_id), decision, payload)
                except Exception as e:
                    log.warning("auto-confirm error: %s", e)

                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
                except asyncio.TimeoutError:
                    pass

