from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.db.models import WorkflowRun, WorkflowStatus


class WorkflowRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def schedule_once(
        self,
        *,
        customer_id: str | None,
        order_id: str | None,
        workflow_type: str,
        stage: str,
        scheduled_for: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        result = await self.session.execute(
            select(WorkflowRun).where(
                WorkflowRun.customer_id == customer_id,
                WorkflowRun.order_id == order_id,
                WorkflowRun.workflow_type == workflow_type,
                WorkflowRun.stage == stage,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        run = WorkflowRun(
            customer_id=customer_id,
            order_id=order_id,
            workflow_type=workflow_type,
            stage=stage,
            scheduled_for=scheduled_for,
            metadata_json=metadata,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def due_runs(self, now: datetime | None = None) -> list[WorkflowRun]:
        now = now or datetime.now(UTC)
        result = await self.session.execute(
            select(WorkflowRun).where(
                WorkflowRun.status == WorkflowStatus.scheduled,
                WorkflowRun.scheduled_for <= now,
            )
        )
        return list(result.scalars().all())

    async def cancel_for_order(self, order_id: str, workflow_types: set[str]) -> int:
        result = await self.session.execute(
            select(WorkflowRun).where(
                WorkflowRun.order_id == order_id,
                WorkflowRun.workflow_type.in_(workflow_types),
                WorkflowRun.status == WorkflowStatus.scheduled,
            )
        )
        runs = result.scalars().all()
        now = datetime.now(UTC)
        for run in runs:
            run.status = WorkflowStatus.cancelled
            run.completed_at = now
        await self.session.flush()
        return len(runs)
