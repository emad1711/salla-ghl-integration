from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.core.config import settings
from salla_ghl.db.models import Customer, Order
from salla_ghl.repositories.workflows import WorkflowRepository


class WorkflowEngine:
    def __init__(self, session: AsyncSession):
        self.repo = WorkflowRepository(session)

    async def schedule_for_order(self, customer: Customer, order: Order | None) -> set[str]:
        if not order:
            return set()

        tags: set[str] = set()
        status = (order.status or "").lower()
        now = datetime.now(UTC)

        if status in {"paid", "completed"}:
            tags.add("salla-post-purchase")
            await self.repo.schedule_once(
                customer_id=customer.id,
                order_id=order.id,
                workflow_type="post_purchase",
                stage="thank_you",
                scheduled_for=now,
                metadata={"tag": "salla-post-purchase"},
            )

        if status in {"delivered", "completed"}:
            await self.repo.schedule_once(
                customer_id=customer.id,
                order_id=order.id,
                workflow_type="review_request",
                stage="review_request",
                scheduled_for=now + timedelta(hours=settings.review_request_delay_hours),
                metadata={"tag": "salla-review-request-due"},
            )

        return tags

    async def schedule_abandoned_cart(self, customer: Customer, cart_id: str | None = None) -> set[str]:
        now = datetime.now(UTC)
        for index, delay in enumerate(settings.abandoned_cart_delays_minutes, start=1):
            await self.repo.schedule_once(
                customer_id=customer.id,
                order_id=None,
                workflow_type="abandoned_cart_recovery",
                stage=f"follow_up_{index}",
                scheduled_for=now + timedelta(minutes=delay),
                metadata={"cart_id": cart_id, "tag": f"salla-cart-abandoned-stage-{index}"},
            )
        return {"salla-cart-abandoned"}

    async def schedule_win_back(self, customer: Customer) -> set[str]:
        await self.repo.schedule_once(
            customer_id=customer.id,
            order_id=None,
            workflow_type="win_back",
            stage="reactivation",
            scheduled_for=datetime.now(UTC),
            metadata={"tag": "salla-winback-due"},
        )
        return {"salla-winback-due"}

    async def cancel_order_followups(self, order: Order) -> int:
        return await self.repo.cancel_for_order(
            order.id,
            {"post_purchase", "review_request", "cross_sell"},
        )
