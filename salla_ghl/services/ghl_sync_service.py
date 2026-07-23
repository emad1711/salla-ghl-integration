import os
from decimal import Decimal, ROUND_FLOOR
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.core.config import settings
from salla_ghl.db.models import Customer, Order
from salla_ghl.integrations.ghl.client import GHLClient


class GHLSyncService:
    def __init__(self, session: AsyncSession):
        self.client = GHLClient(session)

    async def sync_contact(self, customer: Customer, order: Order | None, tags: set[str]) -> str | None:
        payload = self._build_contact_payload(customer, order, tags)
        response = await self.client.upsert_contact(payload)
        contact = response.get("contact") if isinstance(response.get("contact"), dict) else {}
        return contact.get("id")

    async def sync_order_opportunity(self, customer: Customer, order: Order) -> str | None:
        if not settings.ghl_pipeline_id or not settings.ghl_pipeline_stage_id or not customer.ghl_contact_id:
            return None
        payload = self._build_opportunity_payload(customer, order)
        response = await self.client.upsert_opportunity(payload)
        opportunity = response.get("opportunity") if isinstance(response.get("opportunity"), dict) else {}
        return opportunity.get("id")

    def _build_contact_payload(self, customer: Customer, order: Order | None, tags: set[str]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "locationId": settings.ghl_location_id,
            "source": settings.ghl_source,
            "tags": sorted(tags),
        }
        optional_fields = {
            "firstName": customer.first_name,
            "lastName": customer.last_name,
            "email": customer.email,
            "phone": self._phone_value(customer.phone),
        }
        payload.update({key: value for key, value in optional_fields.items() if value})

        custom_fields = []
        field_values = {
            "GHL_CF_SALLA_TOTAL_SPENT": customer.total_spent,
            "GHL_CF_SALLA_PURCHASE_COUNT": customer.purchase_count,
            "GHL_CF_SALLA_LAST_PURCHASE_AT": customer.last_purchase_at,
            "GHL_CF_SALLA_LOYALTY_POINTS": self.loyalty_points(customer),
        }
        if order:
            field_values.update(
                {
                    "GHL_CF_SALLA_ORDER_ID": order.salla_order_id,
                    "GHL_CF_SALLA_ORDER_TOTAL": order.total_amount,
                    "GHL_CF_SALLA_ORDER_STATUS": order.status,
                    "GHL_CF_SALLA_ORDER_ADMIN_URL": order.admin_url,
                }
            )

        for env_key, value in field_values.items():
            field_id = os.getenv(env_key)
            if field_id and value not in (None, "", []):
                custom_fields.append({"id": field_id, "field_value": str(value)})

        if custom_fields:
            payload["customFields"] = custom_fields

        return payload

    def _phone_value(self, phone: Any) -> str | None:
        if phone is None:
            return None
        return str(phone)

    def _build_opportunity_payload(self, customer: Customer, order: Order) -> dict[str, Any]:
        return {
            "locationId": settings.ghl_location_id,
            "pipelineId": settings.ghl_pipeline_id,
            "pipelineStageId": settings.ghl_pipeline_stage_id,
            "contactId": customer.ghl_contact_id,
            "name": f"Salla Order {order.reference_id or order.salla_order_id}",
            "status": settings.ghl_opportunity_status,
            "monetaryValue": float(order.total_amount or 0),
            "source": settings.ghl_source,
        }

    def loyalty_points(self, customer: Customer) -> int:
        spend_points = Decimal(customer.total_spent or 0) * Decimal(str(settings.loyalty_points_per_currency_unit))
        order_points = Decimal(customer.purchase_count or 0) * Decimal(settings.loyalty_points_per_order)
        return int((spend_points + order_points).quantize(Decimal("1"), rounding=ROUND_FLOOR))
