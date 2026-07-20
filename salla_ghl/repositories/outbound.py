from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.core.config import settings
from salla_ghl.db.models import OutboundRequest, OutboundStatus


class OutboundRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        provider: str,
        method: str,
        url: str,
        request_body: dict[str, Any] | None,
    ) -> OutboundRequest:
        row = OutboundRequest(provider=provider, method=method, url=url, request_body=request_body)
        self.session.add(row)
        await self.session.flush()
        return row

    async def mark_response(
        self,
        row: OutboundRequest,
        *,
        status_code: int | None,
        response_body: str | None,
        succeeded: bool,
    ) -> None:
        row.response_status = status_code
        row.response_body = response_body[:5000] if response_body else None
        row.attempt_count += 1
        if succeeded:
            row.status = OutboundStatus.succeeded
            row.next_retry_at = None
        elif row.attempt_count >= settings.max_retry_attempts:
            row.status = OutboundStatus.failed
            row.next_retry_at = None
        else:
            row.status = OutboundStatus.retrying
            delay = settings.retry_base_delay_seconds * (2 ** max(row.attempt_count - 1, 0))
            row.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
        await self.session.flush()
