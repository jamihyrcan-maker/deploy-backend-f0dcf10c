from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RealtimeEvent(BaseModel):
    """
    Generic realtime message envelope.
    """
    type: str = Field(..., examples=["task.created", "queue.updated", "workflow.updated"])
    ts: str = Field(default_factory=utc_now_iso)
    data: Dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = Field(default="backend")
