from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.db.models import GHLEventDelivery, OutboundStatus, now_utc


class GHLEventDeliveryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_dedupe_key(self, dedupe_key: str) -> GHLEventDelivery | None:
        result = await self.session.execute(select(GHLEventDelivery).where(GHLEventDelivery.dedupe_key == dedupe_key))
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        *,
        event_name: str,
        dedupe_key: str,
        request_body: dict[str, Any],
    ) -> tuple[GHLEventDelivery, bool]:
        existing = await self.get_by_dedupe_key(dedupe_key)
        if existing:
            return existing, False

        delivery = GHLEventDelivery(
            event_name=event_name,
            dedupe_key=dedupe_key,
            request_body=request_body,
            status=OutboundStatus.pending,
        )
        self.session.add(delivery)
        await self.session.flush()
        return delivery, True

    async def mark_response(
        self,
        delivery: GHLEventDelivery,
        *,
        status_code: int | None,
        response_body: str | None,
        succeeded: bool,
    ) -> None:
        delivery.response_status = status_code
        delivery.response_body = response_body[:5000] if response_body else None
        delivery.status = OutboundStatus.succeeded if succeeded else OutboundStatus.failed
        delivery.attempt_count += 1
        delivery.updated_at = now_utc()
        await self.session.flush()
