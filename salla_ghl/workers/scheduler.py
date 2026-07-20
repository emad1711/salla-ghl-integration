import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from salla_ghl.core.config import settings
from salla_ghl.core.logging import configure_logging
from salla_ghl.db.models import Customer, Order, WorkflowStatus
from salla_ghl.db.session import SessionLocal, init_db
from salla_ghl.repositories.workflows import WorkflowRepository
from salla_ghl.services.ghl_sync_service import GHLSyncService
from salla_ghl.services.retry_service import RetryService
from salla_ghl.services.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)


async def mark_inactive_customers() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=settings.inactive_days_threshold)
    async with SessionLocal() as session:
        result = await session.execute(
            select(Customer).where(
                Customer.last_purchase_at.is_not(None),
                Customer.last_purchase_at < cutoff,
                Customer.status != "inactive",
            )
        )
        customers = result.scalars().all()
        engine = WorkflowEngine(session)
        for customer in customers:
            customer.status = "inactive"
            await engine.schedule_win_back(customer)
        await session.commit()
        if customers:
            logger.info("Marked inactive customers", extra={"customer_id": ",".join(c.id for c in customers)})


async def complete_due_workflows() -> None:
    async with SessionLocal() as session:
        repo = WorkflowRepository(session)
        ghl = GHLSyncService(session)
        due_runs = await repo.due_runs()
        for run in due_runs:
            customer = None
            order = None
            if run.customer_id:
                customer_result = await session.execute(
                    select(Customer).options(selectinload(Customer.tags)).where(Customer.id == run.customer_id)
                )
                customer = customer_result.scalar_one_or_none()
            if run.order_id:
                order_result = await session.execute(select(Order).where(Order.id == run.order_id))
                order = order_result.scalar_one_or_none()
            if customer:
                active_tags = {tag.tag for tag in customer.tags if tag.active}
                due_tag = (run.metadata_json or {}).get("tag")
                if due_tag:
                    active_tags.add(due_tag)
                await ghl.sync_contact(customer, order, active_tags)
            run.status = WorkflowStatus.completed
            run.completed_at = datetime.now(UTC)
        await session.commit()


async def retry_due_outbound() -> None:
    async with SessionLocal() as session:
        processed = await RetryService(session).process_due_outbound()
        if processed:
            logger.info("Processed outbound retries", extra={"trace_id": str(processed)})


async def scheduler_loop() -> None:
    configure_logging()
    await init_db()
    logger.info("Scheduler started")
    while True:
        await mark_inactive_customers()
        await complete_due_workflows()
        await retry_due_outbound()
        await asyncio.sleep(60)


def main() -> None:
    asyncio.run(scheduler_loop())


if __name__ == "__main__":
    main()
