import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.core.config import settings
from salla_ghl.repositories.outbound import OutboundRepository

logger = logging.getLogger(__name__)


class GHLClientError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GHLClient:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.outbound_repo = OutboundRepository(session)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.ghl_private_integration_token}",
            "Version": settings.ghl_api_version,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        if not settings.ghl_configured:
            raise GHLClientError("Missing GHL_PRIVATE_INTEGRATION_TOKEN or GHL_LOCATION_ID")

        url = f"{settings.ghl_base_url}{path}"
        outbound = await self.outbound_repo.create(provider="ghl", method=method, url=url, request_body=json_body)

        try:
            async with httpx.AsyncClient(timeout=settings.ghl_timeout_seconds) as client:
                response = await client.request(method, url, headers=self.headers, json=json_body)
        except httpx.HTTPError as exc:
            await self.outbound_repo.mark_response(
                outbound,
                status_code=None,
                response_body=str(exc),
                succeeded=False,
            )
            raise GHLClientError(str(exc)) from exc

        succeeded = response.status_code < 400
        await self.outbound_repo.mark_response(
            outbound,
            status_code=response.status_code,
            response_body=response.text,
            succeeded=succeeded,
        )
        if not succeeded:
            logger.error("GHL request failed", extra={"trace_id": response.headers.get("x-request-id")})
            raise GHLClientError("GHL request failed", status_code=response.status_code, response_body=response.text)

        if response.text:
            return response.json()
        return {}

    async def upsert_contact(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/contacts/upsert", payload)

    async def upsert_opportunity(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/opportunities/upsert", payload)
