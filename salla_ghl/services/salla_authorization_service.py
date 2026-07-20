from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.db.models import SallaIntegration
from salla_ghl.repositories.salla_integrations import SallaIntegrationRepository


class SallaAuthorizationError(ValueError):
    pass


class SallaAuthorizationService:
    AUTHORIZE_EVENT = "app.store.authorize"

    def __init__(self, session: AsyncSession):
        self.session = session
        self.integrations = SallaIntegrationRepository(session)

    async def receive_authorization(self, payload: dict[str, Any]) -> SallaIntegration:
        event_type = self._first(payload, ("event",), ("payload", "event"), ("data", "event"))
        if event_type and event_type != self.AUTHORIZE_EVENT:
            raise SallaAuthorizationError(f"Unsupported authorization event: {event_type}")

        access_token = self._first_string(
            payload,
            ("access_token",),
            ("payload", "access_token"),
            ("data", "access_token"),
            ("authorization", "access_token"),
            ("data", "authorization", "access_token"),
        )
        if not access_token:
            raise SallaAuthorizationError("Missing access_token")

        refresh_token = self._first_string(
            payload,
            ("refresh_token",),
            ("payload", "refresh_token"),
            ("data", "refresh_token"),
            ("authorization", "refresh_token"),
            ("data", "authorization", "refresh_token"),
        )
        store_id = self._store_id(payload)
        if not store_id:
            raise SallaAuthorizationError("Missing store_id or merchant id")

        integration = await self.integrations.upsert(
            store_id=store_id,
            store_name=self._store_name(payload),
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=self._expires_at(payload),
        )
        await self.session.commit()
        return integration

    def public_status(self, integration: SallaIntegration | None) -> dict[str, Any]:
        if not integration:
            return {"connected": False, "token_exists": False, "store": None, "expires_at": None}
        return {
            "connected": True,
            "token_exists": bool(integration.access_token),
            "store": {
                "id": integration.store_id,
                "name": integration.store_name,
            },
            "expires_at": integration.expires_at,
            "updated_at": integration.updated_at,
        }

    def public_store(self, integration: SallaIntegration) -> dict[str, Any]:
        return {
            "id": integration.id,
            "store_id": integration.store_id,
            "store_name": integration.store_name,
            "token_exists": bool(integration.access_token),
            "refresh_token_exists": bool(integration.refresh_token),
            "expires_at": integration.expires_at,
            "created_at": integration.created_at,
            "updated_at": integration.updated_at,
        }

    def _store_id(self, payload: dict[str, Any]) -> str | None:
        value = self._first(
            payload,
            ("store_id",),
            ("merchant",),
            ("merchant_id",),
            ("payload", "store_id"),
            ("payload", "merchant"),
            ("payload", "merchant_id"),
            ("data", "store_id"),
            ("data", "merchant_id"),
            ("data", "merchant", "id"),
            ("data", "store", "id"),
            ("merchant", "id"),
            ("store", "id"),
        )
        if isinstance(value, dict):
            value = value.get("id")
        return str(value) if value is not None and str(value).strip() else None

    def _store_name(self, payload: dict[str, Any]) -> str | None:
        value = self._first(
            payload,
            ("store_name",),
            ("merchant_name",),
            ("payload", "store_name"),
            ("payload", "merchant_name"),
            ("data", "store_name"),
            ("data", "merchant_name"),
            ("data", "merchant", "name"),
            ("data", "store", "name"),
            ("merchant", "name"),
            ("store", "name"),
        )
        return str(value) if value is not None and str(value).strip() else None

    def _expires_at(self, payload: dict[str, Any]) -> datetime | None:
        expires_at = self._first(
            payload,
            ("expires_at",),
            ("payload", "expires_at"),
            ("data", "expires_at"),
            ("authorization", "expires_at"),
            ("data", "authorization", "expires_at"),
        )
        parsed = self._parse_datetime(expires_at)
        if parsed:
            return parsed

        expires_in = self._first(
            payload,
            ("expires_in",),
            ("expires",),
            ("payload", "expires_in"),
            ("payload", "expires"),
            ("data", "expires_in"),
            ("data", "expires"),
            ("authorization", "expires_in"),
            ("data", "authorization", "expires_in"),
        )
        try:
            seconds = int(expires_in)
        except (TypeError, ValueError):
            return self._parse_datetime(expires_in)
        return datetime.now(UTC) + timedelta(seconds=seconds)

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, dict):
            value = value.get("date")
        if not isinstance(value, str):
            return None
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def _first_string(self, payload: dict[str, Any], *paths: tuple[str, ...]) -> str | None:
        value = self._first(payload, *paths)
        return str(value) if value is not None and str(value).strip() else None

    def _first(self, payload: dict[str, Any], *paths: tuple[str, ...]) -> Any:
        for path in paths:
            value = self._get(payload, path)
            if value is not None:
                return value
        return None

    def _get(self, payload: dict[str, Any], path: tuple[str, ...]) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        return current
