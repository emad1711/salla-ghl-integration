from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.db.models import EventStatus, WebhookEvent


class EventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_hash(self, payload_hash: str) -> WebhookEvent | None:
        result = await self.session.execute(select(WebhookEvent).where(WebhookEvent.payload_hash == payload_hash))
        return result.scalar_one_or_none()

    async def get(self, event_id: str) -> WebhookEvent | None:
        result = await self.session.execute(select(WebhookEvent).where(WebhookEvent.id == event_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        event_type: str,
        payload_hash: str,
        raw_payload: dict[str, Any],
        event_id: str | None = None,
        merchant_id: str | None = None,
    ) -> tuple[WebhookEvent, bool]:
        existing = await self.get_by_hash(payload_hash)
        if existing:
            return existing, False

        event = WebhookEvent(
            event_id=event_id,
            event_type=event_type,
            merchant_id=merchant_id,
            payload_hash=payload_hash,
            raw_payload=raw_payload,
            status=EventStatus.received,
        )
        self.session.add(event)
        await self.session.flush()
        return event, True

    async def mark_status(self, event: WebhookEvent, status: EventStatus, error_message: str | None = None) -> None:
        event.status = status
        event.error_message = error_message
        if status in {EventStatus.processed, EventStatus.ignored, EventStatus.failed}:
            event.processed_at = datetime.now(UTC)
        await self.session.flush()
