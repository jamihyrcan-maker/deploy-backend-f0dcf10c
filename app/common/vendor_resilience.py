from __future__ import annotations

import os
from typing import Optional

from ..robot_api.service import RobotAPIService
from ..workflow_engine.vendor_task_client import AutoXingTaskClient
from .retry import RetryConfig, async_retry


def _cfg_from_env() -> RetryConfig:
    return RetryConfig(
        retries=int(os.getenv("VENDOR_RETRIES", "3")),
        timeout_s=float(os.getenv("VENDOR_TIMEOUT_S", "12")),
        backoff_base_s=float(os.getenv("VENDOR_BACKOFF_BASE_S", "0.4")),
        backoff_max_s=float(os.getenv("VENDOR_BACKOFF_MAX_S", "4.0")),
        jitter=(os.getenv("VENDOR_BACKOFF_JITTER", "1") != "0"),
    )


class RetryingRobotAPIService:
    """
    Wrap RobotAPIService with retries + per-call timeout.
    """
    def __init__(self, inner: RobotAPIService, cfg: Optional[RetryConfig] = None) -> None:
        self.inner = inner
        self.cfg = cfg or _cfg_from_env()

    async def get_robot_state(self, robot_id: str):
        if hasattr(self.inner, "get_robot_state"):
            return await async_retry(lambda: self.inner.get_robot_state(robot_id), self.cfg)
        return await async_retry(lambda: self.inner.get_state(robot_id), self.cfg)

    async def get_state(self, robot_id: str):
        return await async_retry(lambda: self.inner.get_state(robot_id), self.cfg)

    async def list_pois(self, robot_id: str, only_current_area: bool = True):
        return await async_retry(lambda: self.inner.list_pois(robot_id, only_current_area=only_current_area), self.cfg)


class RetryingTaskClient:
    """
    Wrap AutoXingTaskClient with retries + per-call timeout.
    """
    def __init__(self, inner: AutoXingTaskClient, cfg: Optional[RetryConfig] = None) -> None:
        self.inner = inner
        self.cfg = cfg or _cfg_from_env()

    async def task_create_v3(self, body: dict):
        return await async_retry(lambda: self.inner.task_create_v3(body), self.cfg)

    async def task_state_v2(self, task_id: str):
        return await async_retry(lambda: self.inner.task_state_v2(task_id), self.cfg)

    async def task_cancel(self, task_id: str):
        # Optional: only works if vendor client has a cancel method implemented
        if hasattr(self.inner, "task_cancel"):
            return await async_retry(lambda: self.inner.task_cancel(task_id), self.cfg)
        if hasattr(self.inner, "task_cancel_v3"):
            return await async_retry(lambda: getattr(self.inner, "task_cancel_v3")(task_id), self.cfg)
        if hasattr(self.inner, "task_cancel_v2"):
            return await async_retry(lambda: getattr(self.inner, "task_cancel_v2")(task_id), self.cfg)

        return {"ok": False, "note": "No vendor cancel method implemented in AutoXingTaskClient"}
