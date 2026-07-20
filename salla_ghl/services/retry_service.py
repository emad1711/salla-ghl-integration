import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.core.config import settings
from salla_ghl.db.models import OutboundRequest, OutboundStatus
from salla_ghl.repositories.outbound import OutboundRepository

logger = logging.getLogger(__name__)


class RetryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.outbound = OutboundRepository(session)

    async def process_due_outbound(self) -> int:
        result = await self.session.execute(
            select(OutboundRequest).where(
                OutboundRequest.status == OutboundStatus.retrying,
                OutboundRequest.next_retry_at <= datetime.now(UTC),
            )
        )
        rows = result.scalars().all()
        processed = 0
        for row in rows:
            await self._retry(row)
            processed += 1
        await self.session.commit()
        return processed

    async def _retry(self, row: OutboundRequest) -> None:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if row.provider == "ghl":
            headers.update(
                {
                    "Authorization": f"Bearer {settings.ghl_private_integration_token}",
                    "Version": settings.ghl_api_version,
                }
            )
        try:
            async with httpx.AsyncClient(timeout=settings.ghl_timeout_seconds) as client:
                response = await client.request(row.method, row.url, headers=headers, json=row.request_body)
            await self.outbound.mark_response(
                row,
                status_code=response.status_code,
                response_body=response.text,
                succeeded=response.status_code < 400,
            )
        except httpx.HTTPError as exc:
            logger.warning("Outbound retry failed", extra={"trace_id": row.id})
            await self.outbound.mark_response(row, status_code=None, response_body=str(exc), succeeded=False)
