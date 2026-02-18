from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlmodel import Session, select

from ..persistence.models import Task, TaskStatus, TaskType
from ..priority_manager.service import PriorityService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def base_priority(task_type: TaskType) -> int:
    # Restaurant default (tweak anytime)
    if task_type == TaskType.DELIVERY:
        return 100
    if task_type == TaskType.BILLING:
        return 80
    if task_type == TaskType.ORDERING:
        return 60
    if task_type == TaskType.NAVIGATE:
        return 30
    if task_type == TaskType.CLEANUP:
        return 10
    if task_type == TaskType.CHARGING:
        return 5
    return 0


def aging_bonus_minutes(created_at: datetime) -> float:
    # Every 10 minutes waiting adds +1 priority
    now = utc_now()
    # SQLite drops tzinfo; assume naive timestamps are UTC
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_min = max(0.0, (now - created_at).total_seconds() / 60.0)
    return age_min / 10.0


class QueueManagerService:
    def __init__(self, session: Session):
        self.session = session

    def tick_promote_due_tasks(self) -> int:
        """
        Promote tasks that are due:
          PENDING + release_at <= now  => READY
        Returns number of tasks promoted.
        """
        now = utc_now()

        stmt = select(Task).where(Task.status == TaskStatus.PENDING)
        tasks = list(self.session.exec(stmt).all())

        promoted = 0
        for t in tasks:
            if t.release_at is None:
                t.status = TaskStatus.READY
                t.updated_at = now
                self.session.add(t)
                promoted += 1
            else:
                rel = t.release_at
                if rel is not None and rel.tzinfo is None:
                    rel = rel.replace(tzinfo=timezone.utc)
                if rel is not None and rel <= now:
                    t.status = TaskStatus.READY
                    t.updated_at = now
                    self.session.add(t)
                    promoted += 1

        if promoted:
            self.session.commit()
        return promoted

    def get_ready_queue(self) -> List[Dict[str, Any]]:
        """
        READY tasks (unassigned) ordered by effective priority.
        effective = base_priority + operator_override + aging_bonus
        """
        stmt = (
            select(Task)
            .where(Task.status == TaskStatus.READY)
            .where(Task.assigned_robot_id.is_(None))
        )
        tasks = list(self.session.exec(stmt).all())

        enriched: List[Dict[str, Any]] = []
        for t in tasks:
            override = PriorityService.get_override(self.session, t.id)
            eff = float(base_priority(t.task_type)) + float(override) + float(aging_bonus_minutes(t.created_at))
            enriched.append(
                {
                    "task_id": t.id,
                    "task_type": t.task_type,
                    "status": t.status,
                    "title": t.title,
                    "target_kind": t.target_kind,
                    "target_ref": t.target_ref,
                    "release_at": t.release_at,
                    "created_at": t.created_at,
                    "operator_override": override,
                    "effective_priority": eff,
                }
            )

        enriched.sort(key=lambda x: (-x["effective_priority"], x["created_at"]))
        return enriched

    def stats(self) -> Dict[str, int]:
        all_tasks = list(self.session.exec(select(Task)).all())
        out = {"PENDING": 0, "READY": 0, "ASSIGNED": 0, "DONE": 0, "CANCELED": 0, "TOTAL": 0}
        for t in all_tasks:
            key = t.status.value if hasattr(t.status, "value") else str(t.status)
            out[key] = out.get(key, 0) + 1
            out["TOTAL"] += 1
        return out
