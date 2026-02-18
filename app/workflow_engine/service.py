from __future__ import annotations

import json
import os
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import Session, select

from ..persistence.models import (
    Task,
    TaskStatus,
    TaskType,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStep,
    WorkflowStepType,
)
from ..robot_api.service import RobotAPIService
from ..poi_mapping.service import PoiMappingService
from ..common.safety import safe_mode_enabled
from .vendor_task_client import AutoXingTaskClient


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

logger = logging.getLogger("workflow-engine")
_AUTO_REASSIGN_ON_OFFLINE = os.getenv("AUTO_REASSIGN_ON_OFFLINE", "0") == "1"

class WorkflowEngineService:
    """
    Workflow Engine (protocol-based execution):
      - Expands a Task into protocol steps (Ordering / Delivery / Cleanup)
      - NAVIGATE steps -> creates vendor tasks (AutoXing /task/v3/create runType=22)
      - MANUAL_CONFIRM steps -> waits until operator confirms via API
      - Updates Task status to DONE when workflow finishes
    """

    def __init__(self, session: Session, robot_api: RobotAPIService, task_client: AutoXingTaskClient):
        self.session = session
        self.robot_api = robot_api
        self.task_client = task_client
        self.mapping = PoiMappingService(session)

    # -------------------------
    # Protocol planning
    # -------------------------
    async def plan_steps(self, task: Task, robot_id: str) -> List[WorkflowStep]:
        if task.task_type == TaskType.ORDERING:
            s1 = await self._step_nav(robot_id, "TABLE", task.target_ref, label=f"Ordering: Go to Table {task.target_ref}")
            s2 = self._step_manual("ORDER_DECISION", label="Ordering: Touchscreen (POSTPONE or COMPLETED)")
            return [s1, s2]

        if task.task_type == TaskType.DELIVERY:
            s1 = await self._step_nav(robot_id, "KITCHEN", "main", label="Delivery: Go to Kitchen")
            s2 = self._step_manual("DELIVERY_LOADED", label="Delivery: Chef loaded & verified (CONFIRM)")
            s3 = await self._step_nav(robot_id, "TABLE", task.target_ref, label=f"Delivery: Go to Table {task.target_ref}")
            s4 = self._step_manual("DELIVERY_DONE", label="Delivery: Delivered (CONFIRM)")
            return [s1, s2, s3, s4]

        if task.task_type == TaskType.CLEANUP:
            s1 = await self._step_nav(robot_id, "TABLE", task.target_ref, label=f"Cleanup: Go to Table {task.target_ref}")
            s2 = self._step_manual("CLEANUP_HAS_DISHES", label="Cleanup: Has dishes? (YES/NO)")
            s3 = await self._step_nav(robot_id, "WASHING", "main", label="Cleanup: Go to Washing Machine / Dish Area")
            s4 = self._step_manual("CLEANUP_MORE_DISHES", label="Cleanup: More dishes remaining? (YES/NO)")
            return [s1, s2, s3, s4]

        if task.task_type == TaskType.BILLING:
            s1 = await self._step_nav(robot_id, "OPERATOR", "main", label="Billing: Go to Operator")
            s2 = self._step_manual("BILLING_READY", label="Billing: Operator prepared bill (CONFIRM)")
            s3 = await self._step_nav(robot_id, "TABLE", task.target_ref, label=f"Billing: Go to Table {task.target_ref}")
            s4 = self._step_manual("BILLING_COLLECTED", label="Billing: Payment collected (CONFIRM)")
            s5 = await self._step_nav(robot_id, "OPERATOR", "main", label="Billing: Return to Operator")
            s6 = self._step_manual("BILLING_DONE", label="Billing: Completed (CONFIRM)")
            return [s1, s2, s3, s4, s5, s6]

        if task.task_type == TaskType.NAVIGATE:
            s1 = await self._step_nav(robot_id, task.target_kind, task.target_ref, label=task.title)
            return [s1]

        if task.task_type == TaskType.CHARGING:
            s1 = await self._step_nav(
                robot_id,
                "CHARGING",
                task.target_ref or "main",
                label=task.title or "Charging: Go to charging station",
            )
            return [s1]

        raise ValueError(f"TaskType {task.task_type} not supported in workflow engine yet.")

    def _step_manual(self, step_code: str, label: str) -> WorkflowStep:
        return WorkflowStep(
            run_id=0,
            step_index=0,
            step_type=WorkflowStepType.MANUAL_CONFIRM,
            step_code=step_code,
            label=label,
        )

    async def _step_nav(self, robot_id: str, target_kind: str, target_ref: str, label: str) -> WorkflowStep:
        poi = await self._resolve_poi(robot_id, target_kind, target_ref)
        if not poi:
            raise ValueError(f"Could not resolve POI for target_kind={target_kind}, target_ref={target_ref}")

        coord = poi.coordinate or [None, None]
        x, y = coord[0], coord[1]
        return WorkflowStep(
            run_id=0,
            step_index=0,
            step_type=WorkflowStepType.NAVIGATE,
            step_code="NAVIGATE",
            area_id=poi.areaId,
            x=x,
            y=y,
            yaw=poi.yaw or 0,
            stop_radius=1.0,
            label=label,
        )

    async def _resolve_poi(self, robot_id: str, target_kind: str, target_ref: str):
        """
        Resolution order:
          1) DB Mapping (poi-mapping): (kind, ref) -> poi_id
          2) direct poi id match (if target_ref is actually a poi_id)
          3) name matching fallback (TABLE/KITCHEN/OPERATOR/WASHING)
        """
        kind = (target_kind or "").strip().upper()
        ref = (target_ref or "").strip()

        # 1) Mapping layer
        mapping = self.mapping.get(kind, ref)
        if mapping:
            # Try current area first; if not found, try all areas
            pois = await self.robot_api.list_pois(robot_id, only_current_area=True)
            direct = next((p for p in pois if p.id == mapping.poi_id), None)
            if direct:
                return direct

            pois = await self.robot_api.list_pois(robot_id, only_current_area=False)
            direct = next((p for p in pois if p.id == mapping.poi_id), None)
            if direct:
                return direct
            # If mapping exists but POI not found, continue to fallback logic

        # Pull POIs once for fallback matching
        pois = await self.robot_api.list_pois(robot_id, only_current_area=False)

        # 2) direct id (if user passed poi_id as ref)
        direct = next((p for p in pois if p.id == ref), None)
        if direct:
            return direct

        def norm(s: str) -> str:
            return re.sub(r"\s+", " ", (s or "").strip().lower())

        # 3) fallback by kind + name patterns
        if kind == "TABLE":
            m = re.search(r"(\d+)", ref)
            if not m:
                return None
            num = m.group(1)
            for p in pois:
                name = norm(p.name or "")
                if ("table" in name or "tbl" in name) and num in name:
                    return p
            for p in pois:
                if num in norm(p.name or ""):
                    return p
            return None

        if kind == "KITCHEN":
            for p in pois:
                if "kitchen" in norm(p.name or ""):
                    return p
            return None

        if kind == "OPERATOR":
            for p in pois:
                if "operator" in norm(p.name or ""):
                    return p
            return None

        if kind == "WASHING":
            for p in pois:
                n = norm(p.name or "")
                if "wash" in n or "dish" in n or "sink" in n:
                    return p
            # fallback to kitchen
            for p in pois:
                if "kitchen" in norm(p.name or ""):
                    return p
            return None

        if kind == "CHARGING":
            for p in pois:
                n = norm(p.name or "")
                if "charg" in n or "dock" in n or "pile" in n:
                    return p
            return None

        # final fallback: name contains ref
        ref_n = norm(ref)
        for p in pois:
            if ref_n and ref_n in norm(p.name or ""):
                return p
        return None

    # -------------------------
    # Run lifecycle
    # -------------------------
    async def start_run(self, task_id: int, robot_id: str) -> WorkflowRun:
        task = self.session.get(Task, task_id)
        if not task:
            raise ValueError("Task not found")

        if task.status in (TaskStatus.CANCELED, TaskStatus.DONE):
            raise ValueError(f"Task status is {task.status}; cannot start workflow.")

        running_stmt = select(WorkflowRun).where(
            WorkflowRun.robot_id == robot_id,
            WorkflowRun.status == WorkflowRunStatus.RUNNING,
        )
        if self.session.exec(running_stmt).first() is not None:
            raise ValueError(f"Robot {robot_id} already has a RUNNING workflow.")

        steps = await self.plan_steps(task, robot_id)

        run = WorkflowRun(
            task_id=task_id,
            robot_id=robot_id,
            status=WorkflowRunStatus.RUNNING,
            current_step_index=0,
            total_steps=len(steps),
            current_vendor_task_id=None,
            last_error=None,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        logger.info("workflow.run_created task_id=%s robot_id=%s run_id=%s", task_id, robot_id, run.id)

        for idx, s in enumerate(steps):
            s.run_id = run.id
            s.step_index = idx
            self.session.add(s)

        run.updated_at = utc_now()
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)

        await self._ensure_step_started(run)
        return run

    def get_run(self, run_id: int) -> Optional[WorkflowRun]:
        return self.session.get(WorkflowRun, run_id)

    def get_steps(self, run_id: int) -> List[WorkflowStep]:
        stmt = select(WorkflowStep).where(WorkflowStep.run_id == run_id).order_by(WorkflowStep.step_index.asc())
        return list(self.session.exec(stmt).all())

    async def tick(self) -> Dict[str, int]:
        running_stmt = select(WorkflowRun).where(WorkflowRun.status == WorkflowRunStatus.RUNNING)
        runs = list(self.session.exec(running_stmt).all())

        progressed = 0
        finished = 0
        failed = 0

        for run in runs:
            try:
                changed, done = await self._progress_one_run(run)
                if changed:
                    progressed += 1
                if done:
                    finished += 1
            except Exception as e:
                run.status = WorkflowRunStatus.FAILED
                run.last_error = str(e)
                run.updated_at = utc_now()
                self.session.add(run)
                self.session.commit()
                failed += 1

        return {"progressed_runs": progressed, "finished_runs": finished, "failed_runs": failed}

    async def confirm_current_step(self, run_id: int, decision: str, payload: Optional[dict]) -> WorkflowRun:
        run = self.session.get(WorkflowRun, run_id)
        if not run:
            raise ValueError("Run not found")
        if run.status != WorkflowRunStatus.RUNNING:
            raise ValueError(f"Run is {run.status}, cannot confirm step.")

        steps = self.get_steps(run_id)
        step = next((s for s in steps if s.step_index == run.current_step_index), None)
        if not step:
            raise ValueError("Current step not found")

        if step.step_type != WorkflowStepType.MANUAL_CONFIRM:
            raise ValueError("Current step is not MANUAL_CONFIRM")

        step.completed_at = utc_now()
        step.decision = decision.strip().upper()
        step.decision_payload = json.dumps(payload or {})
        self.session.add(step)
        self.session.commit()
        self.session.refresh(step)

        await self._apply_manual_decision(run, step)
        return run

    async def _apply_manual_decision(self, run: WorkflowRun, step: WorkflowStep) -> None:
        decision = (step.decision or "").upper()
        task = self.session.get(Task, run.task_id)
        if not task:
            raise ValueError("Task not found for run")

        if step.step_code == "ORDER_DECISION":
            if decision == "POSTPONE":
                minutes = int((json.loads(step.decision_payload or "{}")).get("minutes", 10))
                task.release_at = utc_now() + timedelta(minutes=minutes)
                task.status = TaskStatus.PENDING
                task.updated_at = utc_now()

                run.status = WorkflowRunStatus.CANCELED
                run.updated_at = utc_now()

                self.session.add(task)
                self.session.add(run)
                self.session.commit()
                return

            if decision == "COMPLETED":
                task.status = TaskStatus.DONE
                task.updated_at = utc_now()

                run.current_step_index += 1
                run.updated_at = utc_now()

                if run.current_step_index >= run.total_steps:
                    run.status = WorkflowRunStatus.DONE

                self.session.add(task)
                self.session.add(run)
                self.session.commit()
                return

            raise ValueError("ORDER_DECISION expects decision=POSTPONE or COMPLETED")

        if step.step_code == "CLEANUP_HAS_DISHES":
            if decision == "NO":
                task.status = TaskStatus.DONE
                task.updated_at = utc_now()

                run.status = WorkflowRunStatus.DONE
                run.current_step_index = run.total_steps
                run.updated_at = utc_now()

                self.session.add(task)
                self.session.add(run)
                self.session.commit()
                return

            if decision == "YES":
                run.current_step_index += 1
                run.updated_at = utc_now()
                self.session.add(run)
                self.session.commit()
                await self._ensure_step_started(run)
                return

            raise ValueError("CLEANUP_HAS_DISHES expects decision=YES or NO")

        if step.step_code == "CLEANUP_MORE_DISHES":
            if decision == "YES":
                run.current_step_index = 0
                run.current_vendor_task_id = None
                run.updated_at = utc_now()
                self.session.add(run)
                self.session.commit()
                await self._ensure_step_started(run)
                return

            if decision == "NO":
                task.status = TaskStatus.DONE
                task.updated_at = utc_now()

                run.status = WorkflowRunStatus.DONE
                run.current_step_index = run.total_steps
                run.updated_at = utc_now()

                self.session.add(task)
                self.session.add(run)
                self.session.commit()
                return

            raise ValueError("CLEANUP_MORE_DISHES expects decision=YES or NO")

        if step.step_code.startswith("DELIVERY_") or step.step_code.startswith("BILLING_"):
            run.current_step_index += 1
            run.current_vendor_task_id = None
            run.updated_at = utc_now()
            self.session.add(run)
            self.session.commit()

            if run.current_step_index >= run.total_steps:
                run.status = WorkflowRunStatus.DONE
                run.updated_at = utc_now()
                task.status = TaskStatus.DONE
                task.updated_at = utc_now()
                self.session.add(task)
                self.session.add(run)
                self.session.commit()
                return

            await self._ensure_step_started(run)
            return

        run.current_step_index += 1
        run.current_vendor_task_id = None
        run.updated_at = utc_now()
        self.session.add(run)
        self.session.commit()
        await self._ensure_step_started(run)

    async def _progress_one_run(self, run: WorkflowRun) -> Tuple[bool, bool]:
        if _AUTO_REASSIGN_ON_OFFLINE:
            handled = await self._handle_offline_reassign(run)
            if handled:
                return True, True

        if run.current_step_index >= run.total_steps:
            await self._finish_run(run, success=True)
            return True, True

        steps = self.get_steps(run.id)
        step = next((s for s in steps if s.step_index == run.current_step_index), None)
        if not step:
            raise RuntimeError("Workflow step not found")

        if step.step_type == WorkflowStepType.MANUAL_CONFIRM:
            return False, False

        if not run.current_vendor_task_id:
            await self._ensure_step_started(run)
            return True, False

        state = await self.task_client.task_state_v2(run.current_vendor_task_id)
        act_type = (state.get("data") or {}).get("actType")

        if act_type == 1001:
            run.current_step_index += 1
            run.current_vendor_task_id = None
            run.updated_at = utc_now()
            self.session.add(run)
            self.session.commit()

            if run.current_step_index >= run.total_steps:
                await self._finish_run(run, success=True)
                return True, True

            await self._ensure_step_started(run)
            return True, False

        return False, False

    async def _handle_offline_reassign(self, run: WorkflowRun) -> bool:
        try:
            state = await self.robot_api.get_state(run.robot_id)
        except Exception as e:
            logger.warning("workflow.offline_check_failed run_id=%s robot_id=%s err=%s", run.id, run.robot_id, e)
            return False

        online = None
        if hasattr(state, "model_dump"):
            online = state.model_dump().get("isOnline")
        elif hasattr(state, "dict"):
            online = state.dict().get("isOnline")
        elif isinstance(state, dict):
            online = state.get("isOnline")

        if online is not False:
            return False

        # Robot offline -> fail run and re-queue task
        if run.current_vendor_task_id:
            try:
                await self.task_client.task_cancel(run.current_vendor_task_id)
            except Exception as e:
                logger.warning("workflow.vendor_task_cancel_failed run_id=%s vendor_task_id=%s err=%s", run.id, run.current_vendor_task_id, e)

        task = self.session.get(Task, run.task_id)
        if task and task.status not in (TaskStatus.DONE, TaskStatus.CANCELED):
            task.status = TaskStatus.READY
            task.assigned_robot_id = None
            task.updated_at = utc_now()
            self.session.add(task)

        run.status = WorkflowRunStatus.FAILED
        run.last_error = "robot offline -> requeued"
        run.updated_at = utc_now()
        self.session.add(run)
        self.session.commit()
        logger.warning("workflow.reassigned_offline run_id=%s task_id=%s robot_id=%s", run.id, run.task_id, run.robot_id)
        return True

    async def _finish_run(self, run: WorkflowRun, success: bool) -> None:
        task = self.session.get(Task, run.task_id)
        if task and success:
            task.status = TaskStatus.DONE
            task.updated_at = utc_now()
            self.session.add(task)

        run.status = WorkflowRunStatus.DONE if success else WorkflowRunStatus.FAILED
        run.updated_at = utc_now()
        self.session.add(run)
        self.session.commit()

    async def _ensure_step_started(self, run: WorkflowRun) -> None:
        if run.current_step_index >= run.total_steps:
            return

        steps = self.get_steps(run.id)
        step = next((s for s in steps if s.step_index == run.current_step_index), None)
        if not step:
            raise RuntimeError("Workflow step not found")

        if step.step_type == WorkflowStepType.MANUAL_CONFIRM:
            return

        if step.step_type == WorkflowStepType.NAVIGATE:
            if safe_mode_enabled():
                raise ValueError("SAFE_MODE=1 blocks vendor task creation. Set SAFE_MODE=0 to allow.")
            body = self._build_vendor_nav_task(run.robot_id, step)
            resp = await self.task_client.task_create_v3(body)
            vendor_task_id = (resp.get("data") or {}).get("taskId")
            if not vendor_task_id:
                raise RuntimeError(f"Vendor task create returned no taskId: {resp}")

            run.current_vendor_task_id = vendor_task_id
            run.updated_at = utc_now()
            self.session.add(run)
            self.session.commit()
            logger.info("workflow.vendor_task_created run_id=%s vendor_task_id=%s", run.id, vendor_task_id)
            return

        raise ValueError(f"Unsupported step_type in v0: {step.step_type}")

    def _build_vendor_nav_task(self, robot_id: str, step: WorkflowStep) -> Dict[str, Any]:
        if step.area_id is None or step.x is None or step.y is None:
            raise ValueError("NAVIGATE step missing area_id/x/y")

        task_pt = {
            "areaId": step.area_id,
            "x": step.x,
            "y": step.y,
            "yaw": step.yaw or 0,
            "stopRadius": step.stop_radius,
            "type": -1,
            "ext": {"name": step.label or "navigate"},
        }

        return {
            "name": step.label or "Navigate",
            "robotId": robot_id,
            "dispatchType": 0,
            "taskType": 6,
            "runType": 22,
            "runNum": 1,
            "routeMode": 1,
            "runMode": 1,
            "ignorePublicSite": False,
            "taskPts": [task_pt],
        }
