from __future__ import annotations

from pydantic import BaseModel

class OrchestratorTickRequest(BaseModel):
    max_assignments: int = 5


class OrchestratorTickResponse(BaseModel):
    promoted: int
    assigned: int
    progressed_runs: int
    finished_runs: int
    failed_runs: int
