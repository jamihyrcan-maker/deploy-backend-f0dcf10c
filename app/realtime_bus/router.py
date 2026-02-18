from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel, Field

from .bus import bus, publish_event
from .models import RealtimeEvent
from ..auth_roles.deps import require_role, ws_require_role


router = APIRouter(tags=["realtime-bus"])


class PublishRequest(BaseModel):
    type: str = Field(..., examples=["demo.hello", "task.created"])
    data: Dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = Field(default="swagger")


@router.get("/realtime-bus/health", dependencies=[Depends(require_role("monitor"))])
def health():
    return {
        "ok": True,
        "note": "Connect: ws://HOST/ws?api_key=YOUR_KEY . Publish (admin): POST /realtime-bus/publish",
    }


@router.post("/realtime-bus/publish", dependencies=[Depends(require_role("admin"))])
async def publish(payload: PublishRequest):
    sent = await publish_event(payload.type, payload.data, source=payload.source or "swagger")
    return {"ok": True, "sent_to_clients": sent}


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    # Require at least monitor
    principal = await ws_require_role(ws, "monitor")
    if not principal:
        return

    await bus.connect(ws)

    await ws.send_json(
        RealtimeEvent(
            type="ws.connected",
            data={"message": "connected", "role": principal["role"]},
            source="realtime-bus",
        ).model_dump()
    )

    try:
        while True:
            _ = await ws.receive_text()
    except WebSocketDisconnect:
        await bus.disconnect(ws)
    except Exception:
        await bus.disconnect(ws)
