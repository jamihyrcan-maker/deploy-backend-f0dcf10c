from __future__ import annotations

import hashlib
import os
import time
from typing import Any, Dict, List, Optional

import httpx


class AutoXingConfig:
    def __init__(self) -> None:
        """
        Priority:
          1) app/secrets.py (hardcoded locally)
          2) Environment variables
        """
        force_env = os.getenv("AUTOX_FORCE_ENV", "0").strip() not in ("", "0", "false", "False")

        env_base_url = os.getenv("AUTOX_BASE_URL")
        env_app_id = os.getenv("AUTOX_APP_ID")
        env_app_secret = os.getenv("AUTOX_APP_SECRET")
        env_app_code = os.getenv("AUTOX_APP_CODE")

        if env_base_url or env_app_id or env_app_secret or env_app_code:
            self.base_url = env_base_url or "https://apiglobal.autoxing.com"
            self.app_id = env_app_id or ""
            self.app_secret = env_app_secret or ""
            self.app_code = env_app_code or ""
            self.token_ttl_seconds = int(os.getenv("AUTOX_TOKEN_TTL_SECONDS", "3000"))
        elif not force_env:
            # Try secrets.py first
            try:
                from .. import secrets  # type: ignore

                self.base_url = getattr(secrets, "AUTOX_BASE_URL", "https://apiglobal.autoxing.com")
                self.app_id = getattr(secrets, "AUTOX_APP_ID", "")
                self.app_secret = getattr(secrets, "AUTOX_APP_SECRET", "")
                self.app_code = getattr(secrets, "AUTOX_APP_CODE", "")
                self.token_ttl_seconds = int(getattr(secrets, "AUTOX_TOKEN_TTL_SECONDS", 3000))
            except Exception:
                # Fallback to env vars
                self.base_url = os.getenv("AUTOX_BASE_URL", "https://apiglobal.autoxing.com")
                self.app_id = os.getenv("AUTOX_APP_ID", "")
                self.app_secret = os.getenv("AUTOX_APP_SECRET", "")
                self.app_code = os.getenv("AUTOX_APP_CODE", "")
                self.token_ttl_seconds = int(os.getenv("AUTOX_TOKEN_TTL_SECONDS", "3000"))
        else:
            # Forced env with no values set
            self.base_url = os.getenv("AUTOX_BASE_URL", "https://apiglobal.autoxing.com")
            self.app_id = os.getenv("AUTOX_APP_ID", "")
            self.app_secret = os.getenv("AUTOX_APP_SECRET", "")
            self.app_code = os.getenv("AUTOX_APP_CODE", "")
            self.token_ttl_seconds = int(os.getenv("AUTOX_TOKEN_TTL_SECONDS", "3000"))

        if not self.app_id or not self.app_secret or not self.app_code:
            raise RuntimeError(
                "Missing AutoXing credentials. Set app/secrets.py or env vars "
                "(AUTOX_APP_ID, AUTOX_APP_SECRET, AUTOX_APP_CODE)."
            )


class AutoXingTokenCache:
    token: Optional[str] = None
    fetched_at_ms: int = 0


class AutoXingClient:
    """
    Vendor client for AutoXing.
    Only includes:
      - token acquisition (MD5 sign pattern)
      - robot state
      - POI list
    """

    def __init__(self, cfg: AutoXingConfig):
        self.cfg = cfg
        self.cache = AutoXingTokenCache()
        self.http = httpx.AsyncClient()

    @staticmethod
    def _md5_hex(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    async def _fetch_token(self) -> str:
        timestamp = int(time.time() * 1000)
        sign_src = self.cfg.app_id + str(timestamp) + self.cfg.app_secret
        sign = self._md5_hex(sign_src)

        url = f"{self.cfg.base_url}/auth/v1.1/token"
        headers = {"Authorization": f"APPCODE {self.cfg.app_code}", "Content-Type": "application/json"}
        payload = {"appId": self.cfg.app_id, "timestamp": timestamp, "sign": sign}

        resp = await self.http.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != 200:
            raise RuntimeError(f"Auth failed: {data}")

        return data["data"]["token"]

    async def get_token(self) -> str:
        now_ms = int(time.time() * 1000)
        age_sec = (now_ms - self.cache.fetched_at_ms) / 1000.0

        if self.cache.token and age_sec < self.cfg.token_ttl_seconds:
            return self.cache.token

        token = await self._fetch_token()
        self.cache.token = token
        self.cache.fetched_at_ms = now_ms
        return token

    async def _headers(self) -> Dict[str, str]:
        token = await self.get_token()
        return {"X-Token": token}

    async def robot_state(self, robot_id: str) -> Dict[str, Any]:
        url = f"{self.cfg.base_url}/robot/v2.0/{robot_id}/state"
        headers = await self._headers()

        resp = await self.http.get(url, headers=headers, timeout=15)

        # Retry once if token expired
        if resp.status_code in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            resp = await self.http.get(url, headers=headers, timeout=15)

        resp.raise_for_status()
        wrapper = resp.json()
        if wrapper.get("status") in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            resp = await self.http.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            wrapper = resp.json()
        if wrapper.get("status") != 200:
            raise RuntimeError(f"Robot state error: {wrapper}")

        return wrapper["data"]

    async def poi_list(self, robot_id: str) -> List[Dict[str, Any]]:
        url = f"{self.cfg.base_url}/map/v1.1/poi/list"
        headers = await self._headers()
        headers["Content-Type"] = "application/json"
        body = {"robotId": robot_id, "pageSize": 0, "pageNum": 1}

        resp = await self.http.post(url, json=body, headers=headers, timeout=20)

        if resp.status_code in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            headers["Content-Type"] = "application/json"
            resp = await self.http.post(url, json=body, headers=headers, timeout=20)

        resp.raise_for_status()
        wrapper = resp.json()
        if wrapper.get("status") in (401, 403):
            self.cache.token = None
            headers = await self._headers()
            headers["Content-Type"] = "application/json"
            resp = await self.http.post(url, json=body, headers=headers, timeout=20)
            resp.raise_for_status()
            wrapper = resp.json()
        if wrapper.get("status") != 200:
            raise RuntimeError(f"POI list error: {wrapper}")

        return wrapper["data"]["list"]


