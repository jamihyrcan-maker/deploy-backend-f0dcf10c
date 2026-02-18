from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..auth_roles.deps import require_role
from ..assignment_engine.robots import get_robot_ids
from ..common.safety import safe_mode_enabled
from ..persistence.db import get_session, DB_URL
from ..persistence.models import Task
from ..robot_api.autox_client import AutoXingClient, AutoXingConfig

router = APIRouter(prefix="/preflight", tags=["preflight"])


@router.get("/check", dependencies=[Depends(require_role("monitor"))])
async def preflight_check(verify_vendor: bool = False, session: Session = Depends(get_session)) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "safe_mode": safe_mode_enabled(),
        "robot_ids": get_robot_ids(),
        "db": {"ok": False, "url": DB_URL},
        "autox_config": {"ok": False},
    }

    # DB check
    try:
        _ = session.exec(select(Task).limit(1)).first()
        out["db"]["ok"] = True
    except Exception as e:
        out["db"]["error"] = str(e)

    # AutoXing config check (no network)
    try:
        cfg = AutoXingConfig()
        out["autox_config"] = {
            "ok": True,
            "base_url": cfg.base_url,
            "app_id_set": bool(cfg.app_id),
            "app_secret_set": bool(cfg.app_secret),
            "app_code_set": bool(cfg.app_code),
        }
        if verify_vendor:
            try:
                client = AutoXingClient(cfg)
                _ = await client.get_token()
                out["vendor_connectivity"] = {"ok": True}
            except Exception as e:
                out["vendor_connectivity"] = {"ok": False, "error": str(e)}
    except Exception as e:
        out["autox_config"] = {"ok": False, "error": str(e)}

    return out
