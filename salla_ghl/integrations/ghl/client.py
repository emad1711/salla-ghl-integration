import json
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

    def _masked_headers(self) -> dict[str, str]:
        headers = self.headers.copy()
        if headers.get("Authorization"):
            headers["Authorization"] = "Bearer ***"
        return headers

    def _response_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return None

    def _validation_errors(self, response_json: Any) -> Any:
        if not isinstance(response_json, dict):
            return None
        for key in ("errors", "error", "message", "details"):
            if key in response_json:
                return response_json[key]
        return None

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
            logger.error(
                "GHL request failed %s",
                json.dumps(
                    {
                        "method": method,
                        "path": path,
                        "url": url,
                        "request_headers": self._masked_headers(),
                        "request_payload": json_body,
                        "status_code": None,
                        "response_text": str(exc),
                        "response_json": None,
                        "validation_errors": None,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
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
            response_json = self._response_json(response)
            logger.error(
                "GHL request failed %s",
                json.dumps(
                    {
                        "method": method,
                        "path": path,
                        "url": url,
                        "request_headers": self._masked_headers(),
                        "request_payload": json_body,
                        "status_code": response.status_code,
                        "response_text": response.text,
                        "response_json": response_json,
                        "validation_errors": self._validation_errors(response_json),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                extra={"trace_id": response.headers.get("x-request-id")},
            )
            raise GHLClientError("GHL request failed", status_code=response.status_code, response_body=response.text)

        if response.text:
            return response.json()
        return {}

    async def upsert_contact(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/contacts/upsert", payload)

    async def upsert_opportunity(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/opportunities/upsert", payload)
