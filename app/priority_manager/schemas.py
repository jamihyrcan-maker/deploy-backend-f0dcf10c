from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class SetOverrideRequest(BaseModel):
    task_id: int
    override: int = Field(..., description="Positive bumps priority, negative demotes.")
    reason: Optional[str] = None


class SetOverrideResponse(BaseModel):
    ok: bool
    task_id: int
    override: int


class ClearOverrideResponse(BaseModel):
    ok: bool
    task_id: int
