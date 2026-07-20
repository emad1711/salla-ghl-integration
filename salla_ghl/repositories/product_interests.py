from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from salla_ghl.db.models import Customer, ProductInterest, now_utc


class ProductInterestRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_interest(
        self,
        *,
        customer_id: str,
        product_id: str | None,
        sku: str | None,
        product_name: str | None,
        source: str,
    ) -> ProductInterest:
        result = await self.session.execute(
            select(ProductInterest).where(
                ProductInterest.customer_id == customer_id,
                ProductInterest.salla_product_id == product_id,
                ProductInterest.sku == sku,
            )
        )
        interest = result.scalar_one_or_none()
        if not interest:
            interest = ProductInterest(
                customer_id=customer_id,
                salla_product_id=product_id,
                sku=sku,
                product_name=product_name,
                source=source,
                active=True,
            )
            self.session.add(interest)
        else:
            interest.product_name = product_name or interest.product_name
            interest.source = source or interest.source
            interest.active = True
            interest.updated_at = now_utc()
        await self.session.flush()
        return interest

    async def interested_customers(
        self,
        *,
        product_id: str | None,
        sku: str | None,
    ) -> list[tuple[Customer, ProductInterest]]:
        clauses = []
        if product_id:
            clauses.append(ProductInterest.salla_product_id == product_id)
        if sku:
            clauses.append(ProductInterest.sku == sku)
        if not clauses:
            return []

        result = await self.session.execute(
            select(ProductInterest)
            .options(selectinload(ProductInterest.customer).selectinload(Customer.tags))
            .where(ProductInterest.active.is_(True), or_(*clauses))
        )
        return [(interest.customer, interest) for interest in result.scalars().all() if interest.customer]

    async def mark_notified(self, interest: ProductInterest) -> None:
        interest.notified_at = now_utc()
        interest.active = False
        interest.updated_at = now_utc()
        await self.session.flush()
