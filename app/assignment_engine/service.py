from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import update
from sqlmodel import Session, select

from ..persistence.models import Task, TaskStatus, WorkflowRun, WorkflowRunStatus
from ..robot_api.service import RobotAPIService
from ..workflow_engine.service import WorkflowEngineService
from ..workflow_engine.vendor_task_client import AutoXingTaskClient
from ..queue_manager.service import QueueManagerService
from .robots import get_robot_ids


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_bool(d: Any, *keys: str) -> Optional[bool]:
    if d is None:
        return None
    if hasattr(d, "model_dump"):
        d = d.model_dump()
    elif hasattr(d, "dict"):
        d = d.dict()
    if isinstance(d, dict):
        for k in keys:
            v = d.get(k)
            if isinstance(v, bool):
                return v
    return None


class AssignmentEngineService:
    """
    Assignment Engine v0 + Priority:
      - Uses QueueManagerService.get_ready_queue() (sorted by effective priority)
      - Picks an eligible robot (not busy, online, not charging, not estop)
      - Atomically claims the task
      - Starts workflow run
    """

    def __init__(self, session: Session, robot_api: RobotAPIService, task_client: AutoXingTaskClient):
        self.session = session
        self.robot_api = robot_api
        self.task_client = task_client

    async def list_robots(self, include_state: bool = False) -> List[Dict[str, Any]]:
        ids = get_robot_ids()
        robots = []
        for rid in ids:
            busy = self._is_robot_busy(rid)
            eligible, reason, state_obj = await self._is_robot_eligible(rid, include_state=include_state)
            robots.append(
                {
                    "robot_id": rid,
                    "busy": busy,
                    "eligible": eligible and (not busy),
                    "reason": reason if (not eligible or busy) else None,
                    "state": state_obj if include_state else None,
                }
            )
        return robots

    def _is_robot_busy(self, robot_id: str) -> bool:
        stmt = select(WorkflowRun).where(
            WorkflowRun.robot_id == robot_id,
            WorkflowRun.status == WorkflowRunStatus.RUNNING,
        )
        return self.session.exec(stmt).first() is not None

    async def _is_robot_eligible(self, robot_id: str, include_state: bool = False) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        state = await self.robot_api.get_state(robot_id)

        state_dict: Optional[Dict[str, Any]] = None
        if include_state:
            if hasattr(state, "model_dump"):
                state_dict = state.model_dump()
            elif hasattr(state, "dict"):
                state_dict = state.dict()
            elif isinstance(state, dict):
                state_dict = state

        online = _safe_bool(state, "online", "isOnline", "connected")
        charging = _safe_bool(state, "charging", "isCharging", "onCharge", "onChargingPile")
        estop = _safe_bool(state, "emergency_stop", "emergencyStop", "eStop")

        if online is False:
            return False, "robot offline", state_dict
        if charging is True:
            return False, "robot charging", state_dict
        if estop is True:
            return False, "emergency stop active", state_dict

        return True, None, state_dict

    def _pick_next_ready_task_id(self) -> Optional[int]:
        qm = QueueManagerService(self.session)
        q = qm.get_ready_queue()
        if not q:
            return None
        return int(q[0]["task_id"])

    def _try_claim_task(self, task_id: int, robot_id: str) -> bool:
        now = utc_now()
        stmt = (
            update(Task)
            .where(Task.id == task_id)
            .where(Task.status == TaskStatus.READY)
            .where(Task.assigned_robot_id.is_(None))
            .values(status=TaskStatus.ASSIGNED, assigned_robot_id=robot_id, updated_at=now)
        )
        res = self.session.exec(stmt)
        self.session.commit()
        return getattr(res, "rowcount", 0) == 1

    async def assign_next(self, preferred_robot_id: Optional[str] = None, include_robot_state: bool = False) -> Dict[str, Any]:
        robot_ids = get_robot_ids()
        if not robot_ids:
            return {"assigned": False, "message": "No robots configured. Set ROBOT_IDS env var or secrets.ROBOT_IDS."}

        task_id = self._pick_next_ready_task_id()
        if task_id is None:
            return {"assigned": False, "message": "No READY tasks to assign."}

        candidates = [preferred_robot_id] if preferred_robot_id else robot_ids
        chosen_robot = None
        chosen_reason = None
        chosen_state = None

        for rid in candidates:
            if rid not in robot_ids:
                continue
            if self._is_robot_busy(rid):
                chosen_reason = "robot busy"
                continue
            ok, reason, state_obj = await self._is_robot_eligible(rid, include_state=include_robot_state)
            if ok:
                chosen_robot = rid
                chosen_state = state_obj
                break
            chosen_reason = reason

        if not chosen_robot:
            return {"assigned": False, "message": f"No eligible robot found ({chosen_reason or 'unknown'})."}

        if not self._try_claim_task(task_id, chosen_robot):
            return {"assigned": False, "message": "Task was already claimed by another process/operator."}

        wf = WorkflowEngineService(self.session, self.robot_api, self.task_client)
        run = await wf.start_run(task_id, chosen_robot)

        return {
            "assigned": True,
            "task_id": task_id,
            "robot_id": chosen_robot,
            "run_id": run.id,
            "message": "Assigned task (priority) and started workflow run.",
            "robot_state": chosen_state if include_robot_state else None,
        }

    def get_assignments(self) -> Dict[str, Any]:
        t_stmt = select(Task).where(Task.status == TaskStatus.ASSIGNED).order_by(Task.updated_at.desc())
        tasks = list(self.session.exec(t_stmt).all())

        r_stmt = select(WorkflowRun).where(WorkflowRun.status == WorkflowRunStatus.RUNNING).order_by(WorkflowRun.updated_at.desc())
        runs = list(self.session.exec(r_stmt).all())

        return {
            "assigned_tasks": [
                {
                    "task_id": t.id,
                    "task_type": t.task_type,
                    "status": t.status,
                    "title": t.title,
                    "target_kind": t.target_kind,
                    "target_ref": t.target_ref,
                    "assigned_robot_id": t.assigned_robot_id,
                    "updated_at": t.updated_at,
                }
                for t in tasks
            ],
            "running_workflows": [
                {
                    "run_id": r.id,
                    "task_id": r.task_id,
                    "robot_id": r.robot_id,
                    "status": r.status,
                    "current_step_index": r.current_step_index,
                    "total_steps": r.total_steps,
                    "current_vendor_task_id": r.current_vendor_task_id,
                    "updated_at": r.updated_at,
                    "last_error": r.last_error,
                }
                for r in runs
            ],
        }

    def unassign(self, task_id: int, reason: Optional[str] = None) -> bool:
        task = self.session.get(Task, task_id)
        if not task:
            return False
        if task.status != TaskStatus.ASSIGNED:
            return False

        task.status = TaskStatus.READY
        task.assigned_robot_id = None
        task.updated_at = utc_now()
        if reason:
            task.notes = (task.notes or "") + f"\n[UNASSIGN] {reason}"
        self.session.add(task)
        self.session.commit()
        return True
