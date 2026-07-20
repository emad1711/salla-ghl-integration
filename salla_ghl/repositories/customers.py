from datetime import datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.db.models import Customer, CustomerTag, now_utc


class CustomerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_identity(
        self,
        *,
        salla_customer_id: str | None,
        email: str | None,
        phone: str | None,
    ) -> Customer | None:
        clauses = []
        if salla_customer_id:
            clauses.append(Customer.salla_customer_id == salla_customer_id)
        if email:
            clauses.append(Customer.email == email.lower())
        if phone:
            clauses.append(Customer.phone == phone)
        if not clauses:
            return None
        result = await self.session.execute(select(Customer).where(or_(*clauses)))
        return result.scalars().first()

    async def upsert_identity(
        self,
        *,
        salla_customer_id: str | None,
        email: str | None,
        phone: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> Customer:
        normalized_email = email.lower() if email else None
        customer = await self.find_by_identity(
            salla_customer_id=salla_customer_id,
            email=normalized_email,
            phone=phone,
        )
        if not customer:
            customer = Customer(
                salla_customer_id=salla_customer_id,
                email=normalized_email,
                phone=phone,
                first_name=first_name,
                last_name=last_name,
            )
            self.session.add(customer)
        else:
            customer.salla_customer_id = customer.salla_customer_id or salla_customer_id
            customer.email = customer.email or normalized_email
            customer.phone = customer.phone or phone
            customer.first_name = first_name or customer.first_name
            customer.last_name = last_name or customer.last_name
            customer.updated_at = now_utc()
        await self.session.flush()
        return customer

    async def update_metrics(
        self,
        customer: Customer,
        *,
        total_spent: Decimal,
        purchase_count: int,
        last_purchase_at: datetime | None,
    ) -> Customer:
        customer.total_spent = total_spent
        customer.purchase_count = purchase_count
        customer.last_purchase_at = last_purchase_at
        if purchase_count <= 1:
            customer.status = "new"
        elif customer.status != "inactive":
            customer.status = "returning"
        customer.updated_at = now_utc()
        await self.session.flush()
        return customer

    async def set_ghl_contact_id(self, customer: Customer, ghl_contact_id: str | None) -> None:
        if ghl_contact_id:
            customer.ghl_contact_id = ghl_contact_id
            customer.updated_at = now_utc()
            await self.session.flush()

    async def sync_tags(self, customer: Customer, tags: set[str]) -> None:
        result = await self.session.execute(select(CustomerTag).where(CustomerTag.customer_id == customer.id))
        existing = {row.tag: row for row in result.scalars().all()}

        for tag in tags:
            row = existing.get(tag)
            if row:
                row.active = True
                row.removed_at = None
            else:
                self.session.add(CustomerTag(customer_id=customer.id, tag=tag, active=True))

        for tag, row in existing.items():
            if row.source == "salla" and tag not in tags and row.active:
                row.active = False
                row.removed_at = now_utc()

        await self.session.flush()
