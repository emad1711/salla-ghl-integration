from typing import Any

import httpx

from salla_ghl.core.config import settings


class SallaClientError(RuntimeError):
    pass


class SallaClient:
    def __init__(self, access_token: str | None = None):
        self.access_token = access_token

    @property
    def headers(self) -> dict[str, str]:
        token = self.access_token or settings.salla_api_token
        if not token:
            raise SallaClientError("Missing Salla access token")
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def request(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                f"{settings.salla_api_base_url}{path}",
                headers=self.headers,
                params=params,
            )
        if response.status_code >= 400:
            raise SallaClientError(f"Salla API failed: {response.status_code} {response.text}")
        return response.json()

    async def list_orders(self, page: int = 1, per_page: int = 50) -> dict[str, Any]:
        return await self.request("GET", "/orders", {"page": page, "per_page": per_page})

    async def list_customers(self, page: int = 1, per_page: int = 50) -> dict[str, Any]:
        return await self.request("GET", "/customers", {"page": page, "per_page": per_page})

    async def list_abandoned_carts(
        self,
        *,
        page: int = 1,
        per_page: int = 50,
        offset: int | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if offset is not None:
            params["offset"] = offset
        if keyword:
            params["keyword"] = keyword
        return await self.request("GET", "/carts/abandoned", params)
