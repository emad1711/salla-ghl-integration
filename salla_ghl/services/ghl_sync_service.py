import os
from decimal import Decimal, ROUND_FLOOR
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.core.config import settings
from salla_ghl.db.models import Customer, Order, OutboundStatus, now_utc
from salla_ghl.integrations.ghl.client import GHLClient
from salla_ghl.integrations.salla.normalizer import NormalizedCart
from salla_ghl.repositories.ghl_event_deliveries import GHLEventDeliveryRepository


class GHLSyncService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.client = GHLClient(session)
        self.event_deliveries = GHLEventDeliveryRepository(session)

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

    async def trigger_abandoned_checkout_webhook(
        self,
        *,
        customer: Customer,
        cart: NormalizedCart,
        contact_id: str | None,
        tags: set[str],
    ) -> dict[str, Any]:
        if not settings.ghl_abandoned_checkout_webhook_url:
            return {"sent": False, "reason": "missing_webhook_url"}
        if not contact_id:
            return {"sent": False, "reason": "missing_contact_id"}

        payload = self._build_abandoned_checkout_payload(customer=customer, cart=cart, contact_id=contact_id, tags=tags)
        dedupe_key = self._abandoned_checkout_dedupe_key(contact_id=contact_id, cart=cart)
        delivery, created = await self.event_deliveries.get_or_create(
            event_name="salla.cart_abandoned",
            dedupe_key=dedupe_key,
            request_body=payload,
        )
        if not created and delivery.status == OutboundStatus.succeeded:
            return {"sent": False, "reason": "duplicate", "dedupe_key": dedupe_key}

        delivery.request_body = payload
        delivery.status = OutboundStatus.pending
        await self.session.flush()

        try:
            response = await self.client.post_inbound_webhook(settings.ghl_abandoned_checkout_webhook_url, payload)
        except Exception as exc:
            await self.event_deliveries.mark_response(
                delivery,
                status_code=getattr(exc, "status_code", None),
                response_body=getattr(exc, "response_body", None) or str(exc),
                succeeded=False,
            )
            raise

        await self.event_deliveries.mark_response(
            delivery,
            status_code=response.get("status_code"),
            response_body=str(response.get("body")),
            succeeded=True,
        )
        return {"sent": True, "dedupe_key": dedupe_key, "response": response}

    def _build_abandoned_checkout_payload(
        self,
        *,
        customer: Customer,
        cart: NormalizedCart,
        contact_id: str,
        tags: set[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event": "abandoned.cart",
            "eventTimestamp": now_utc().isoformat(),
            "locationId": settings.ghl_location_id,
            "contactId": contact_id,
            "email": customer.email,
            "phone": self._phone_value(customer.phone),
            "sallaCustomerId": customer.salla_customer_id,
            "sallaCartId": cart.salla_cart_id,
            "cartTotal": float(cart.total_amount or 0),
            "currency": cart.currency,
            "customer": {
                "email": customer.email,
                "phone": self._phone_value(customer.phone),
                "firstName": customer.first_name,
                "lastName": customer.last_name,
            },
            "items": [
                {
                    "productId": item.product_id,
                    "sku": item.sku,
                    "name": item.name,
                    "quantity": item.quantity,
                    "unitPrice": float(item.unit_price or 0),
                    "totalPrice": float(item.total_price or 0),
                }
                for item in cart.items
            ],
            "tags": sorted(tags),
        }
        if cart.checkout_url:
            payload["checkoutUrl"] = cart.checkout_url
        return payload

    def _abandoned_checkout_dedupe_key(self, *, contact_id: str, cart: NormalizedCart) -> str:
        cart_identity = cart.salla_cart_id or cart.checkout_url or "unknown-cart"
        return f"ghl:abandoned_checkout:{settings.ghl_location_id}:{contact_id}:{cart_identity}"

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
