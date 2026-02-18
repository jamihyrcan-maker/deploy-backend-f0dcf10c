from __future__ import annotations

import asyncio
from typing import Any, Dict, Set

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from .models import RealtimeEvent


class BroadcastBus:
    """
    In-memory WebSocket broadcaster (v0).
    - Holds active websocket connections
    - Broadcasts JSON events to all clients
    """
    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: RealtimeEvent) -> int:
        """
        Broadcast event to all connected clients.
        Returns count of successfully sent clients.
        """
        payload = event.model_dump()
        async with self._lock:
            clients = list(self._clients)

        sent = 0
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                if ws.client_state != WebSocketState.CONNECTED:
                    dead.append(ws)
                    continue
                await ws.send_json(payload)
                sent += 1
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

        return sent


# Global singleton bus
bus = BroadcastBus()


async def publish_event(event_type: str, data: Dict[str, Any] | None = None, source: str = "backend") -> int:
    """
    Async publish (best for async routes/services).
    """
    ev = RealtimeEvent(type=event_type, data=data or {}, source=source)
    return await bus.broadcast(ev)


def publish_event_nowait(event_type: str, data: Dict[str, Any] | None = None, source: str = "backend") -> None:
    """
    Fire-and-forget publish.
    Safe to call from sync endpoints (it schedules on the running loop).
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(publish_event(event_type, data=data, source=source))
    except RuntimeError:
        # no running loop (rare in FastAPI), skip silently
        return
