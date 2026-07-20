from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from salla_ghl.core.config import settings
from salla_ghl.db.models import Order, OrderItem


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_salla_id(self, salla_order_id: str) -> Order | None:
        result = await self.session.execute(
            select(Order).options(selectinload(Order.items)).where(Order.salla_order_id == salla_order_id)
        )
        return result.scalar_one_or_none()

    async def upsert_order(
        self,
        *,
        salla_order_id: str,
        reference_id: str | None,
        customer_id: str | None,
        status: str | None,
        payment_status: str | None,
        fulfillment_status: str | None,
        total_amount: Decimal,
        currency: str,
        admin_url: str | None,
    ) -> Order:
        order = await self.get_by_salla_id(salla_order_id)
        if not order:
            order = Order(
                salla_order_id=salla_order_id,
                reference_id=reference_id,
                customer_id=customer_id,
                status=status,
                payment_status=payment_status,
                fulfillment_status=fulfillment_status,
                total_amount=total_amount,
                currency=currency,
                admin_url=admin_url,
            )
            self.session.add(order)
        else:
            order.reference_id = reference_id or order.reference_id
            order.customer_id = customer_id or order.customer_id
            order.status = status or order.status
            order.payment_status = payment_status or order.payment_status
            order.fulfillment_status = fulfillment_status or order.fulfillment_status
            order.total_amount = total_amount
            order.currency = currency or order.currency
            order.admin_url = admin_url or order.admin_url
        await self.session.flush()
        return order

    async def replace_items(self, order: Order, items: list[dict[str, object]]) -> None:
        await self.session.execute(delete(OrderItem).where(OrderItem.order_id == order.id))
        for item in items:
            self.session.add(
                OrderItem(
                    order_id=order.id,
                    salla_product_id=item.get("product_id"),
                    sku=item.get("sku"),
                    name=item.get("name"),
                    quantity=int(item.get("quantity") or 1),
                    unit_price=Decimal(str(item.get("unit_price") or 0)),
                    total_price=Decimal(str(item.get("total_price") or 0)),
                )
            )
        await self.session.flush()

    async def customer_metrics(self, customer_id: str) -> tuple[Decimal, int, object]:
        result = await self.session.execute(
            select(
                func.coalesce(func.sum(Order.total_amount), 0),
                func.count(Order.id),
                func.max(Order.created_at),
            ).where(
                Order.customer_id == customer_id,
                Order.status.in_(settings.loyalty_eligible_statuses),
            )
        )
        total, count, last_purchase_at = result.one()
        return Decimal(str(total or 0)), int(count or 0), last_purchase_at
