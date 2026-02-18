from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from ..robot_api.autox_client import AutoXingClient, AutoXingConfig


class AutoXingTaskClient(AutoXingClient):
    """
    Extends the existing AutoXingClient with task APIs needed for execution.
    We keep Robot API block untouched by adding this in the workflow engine.
    """

    async def task_create_v3(self, body: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.cfg.base_url}/task/v3/create"
        headers = await self._headers()
        headers["Content-Type"] = "application/json"

        resp = await self.http.post(url, json=body, headers=headers, timeout=20)

        if resp.status_code in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            headers["Content-Type"] = "application/json"
            resp = await self.http.post(url, json=body, headers=headers, timeout=20)

        resp.raise_for_status()
        data = resp.json()
        if data.get("status") in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            headers["Content-Type"] = "application/json"
            resp = await self.http.post(url, json=body, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") != 200:
            raise RuntimeError(f"Task create error: {data}")
        return data

    async def task_state_v2(self, task_id: str) -> Dict[str, Any]:
        url = f"{self.cfg.base_url}/task/v2.0/{task_id}/state"
        headers = await self._headers()

        resp = await self.http.get(url, headers=headers, timeout=15)

        if resp.status_code in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            resp = await self.http.get(url, headers=headers, timeout=15)

        resp.raise_for_status()
        data = resp.json()
        if data.get("status") in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            resp = await self.http.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        return data

    async def task_cancel_v3(self, task_id: str) -> Dict[str, Any]:
        url = f"{self.cfg.base_url}/task/v3/cancel"
        headers = await self._headers()
        headers["Content-Type"] = "application/json"
        body = {"taskId": task_id}

        resp = await self.http.post(url, json=body, headers=headers, timeout=15)
        if resp.status_code in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            headers["Content-Type"] = "application/json"
            resp = await self.http.post(url, json=body, headers=headers, timeout=15)

        resp.raise_for_status()
        data = resp.json()
        if data.get("status") in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            headers["Content-Type"] = "application/json"
            resp = await self.http.post(url, json=body, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        return data

    async def task_cancel_v2(self, task_id: str) -> Dict[str, Any]:
        url = f"{self.cfg.base_url}/task/v2.0/{task_id}/cancel"
        headers = await self._headers()

        resp = await self.http.post(url, headers=headers, timeout=15)
        if resp.status_code in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            resp = await self.http.post(url, headers=headers, timeout=15)

        resp.raise_for_status()
        data = resp.json()
        if data.get("status") in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            resp = await self.http.post(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        return data

    async def task_cancel(self, task_id: str) -> Dict[str, Any]:
        # Prefer v3, fallback to v2
        try:
            return await self.task_cancel_v3(task_id)
        except httpx.HTTPStatusError:
            return await self.task_cancel_v2(task_id)
