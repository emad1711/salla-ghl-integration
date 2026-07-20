import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.core.config import settings
from salla_ghl.core.security import payload_hash
from salla_ghl.db.models import EventStatus
from salla_ghl.integrations.salla.normalizer import NormalizedEvent, SallaNormalizer, normalize_tag
from salla_ghl.repositories.customers import CustomerRepository
from salla_ghl.repositories.events import EventRepository
from salla_ghl.repositories.orders import OrderRepository
from salla_ghl.repositories.product_interests import ProductInterestRepository
from salla_ghl.services.ghl_sync_service import GHLSyncService
from salla_ghl.services.segmentation_service import SegmentationService
from salla_ghl.services.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)


class EventService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.events = EventRepository(session)
        self.customers = CustomerRepository(session)
        self.orders = OrderRepository(session)
        self.product_interests = ProductInterestRepository(session)
        self.normalizer = SallaNormalizer()
        self.segmentation = SegmentationService()
        self.workflow_engine = WorkflowEngine(session)
        self.ghl = GHLSyncService(session)

    async def receive(self, raw_body: bytes) -> tuple[str, bool, str]:
        payload = json.loads(raw_body.decode("utf-8"))
        normalized = self.normalizer.normalize(payload)
        event, created = await self.events.create(
            event_type=normalized.event_type,
            event_id=normalized.event_id,
            merchant_id=normalized.merchant_id,
            payload_hash=payload_hash(raw_body),
            raw_payload=payload,
        )
        if not created:
            await self.events.mark_status(event, EventStatus.ignored)
            await self.session.commit()
            return event.id, False, "duplicate"

        if normalized.event_type not in settings.salla_allowed_events:
            await self.events.mark_status(event, EventStatus.ignored, "Unsupported event")
            await self.session.commit()
            return event.id, False, "ignored"

        await self.events.mark_status(event, EventStatus.queued)
        await self.session.commit()
        return event.id, True, "queued"

    async def process_event(self, event_id: str) -> dict[str, Any]:
        event = await self.events.get(event_id)
        if not event:
            raise ValueError(f"Webhook event not found: {event_id}")
        if event.status == EventStatus.processed:
            return {"ok": True, "event_id": event_id, "already_processed": True}

        await self.events.mark_status(event, EventStatus.processing)
        await self.session.flush()

        try:
            normalized = self.normalizer.normalize(event.raw_payload)
            result = await self._process_normalized(normalized)
            await self.events.mark_status(event, EventStatus.processed)
            await self.session.commit()
            return {"ok": True, "event_id": event_id, **result}
        except Exception as exc:
            event.retry_count += 1
            await self.events.mark_status(event, EventStatus.failed, str(exc))
            await self.session.commit()
            logger.exception("Failed to process event", extra={"event_id": event_id, "event_type": event.event_type})
            raise

    async def _process_normalized(self, normalized: NormalizedEvent) -> dict[str, Any]:
        if not normalized.customer:
            if normalized.product_stock:
                return await self._process_product_stock(normalized)
            return {"ignored": True, "reason": "missing_customer"}

        customer = await self.customers.upsert_identity(
            salla_customer_id=normalized.customer.salla_customer_id,
            email=normalized.customer.email,
            phone=normalized.customer.phone,
            first_name=normalized.customer.first_name,
            last_name=normalized.customer.last_name,
        )

        order = None
        product_skus: list[str] = []
        if normalized.order:
            order = await self.orders.upsert_order(
                salla_order_id=normalized.order.salla_order_id,
                reference_id=normalized.order.reference_id,
                customer_id=customer.id,
                status=normalized.order.status,
                payment_status=normalized.order.payment_status,
                fulfillment_status=normalized.order.fulfillment_status,
                total_amount=normalized.order.total_amount,
                currency=normalized.order.currency,
                admin_url=normalized.order.admin_url,
            )
            await self.orders.replace_items(
                order,
                [
                    {
                        "product_id": item.product_id,
                        "sku": item.sku,
                        "name": item.name,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                        "total_price": item.total_price,
                    }
                    for item in normalized.order.items
                ],
            )
            product_skus = [item.sku for item in normalized.order.items if item.sku]
            total_spent, purchase_count, last_purchase_at = await self.orders.customer_metrics(customer.id)
            await self.customers.update_metrics(
                customer,
                total_spent=total_spent,
                purchase_count=purchase_count,
                last_purchase_at=last_purchase_at,
            )

        tags = self.segmentation.tags_for_customer(customer, order, product_skus)
        tags.update(self._event_tags(normalized))
        tags.update(await self.workflow_engine.schedule_for_order(customer, order))
        if normalized.cart:
            tags.update(await self.workflow_engine.schedule_abandoned_cart(customer, normalized.cart.salla_cart_id))
            await self._record_product_interests(customer.id, normalized.cart.items, source="abandoned_cart")
        if order and self._is_cancel_or_refund(normalized):
            cancelled_count = await self.workflow_engine.cancel_order_followups(order)
            if cancelled_count:
                tags.add("salla-workflows-cancelled")
        await self.customers.sync_tags(customer, tags)
        ghl_contact_id = await self.ghl.sync_contact(customer, order, tags)
        await self.customers.set_ghl_contact_id(customer, ghl_contact_id)
        opportunity_id = None
        if order and normalized.event_type == "order.created":
            opportunity_id = await self.ghl.sync_order_opportunity(customer, order)

        return {
            "sent_to_ghl": True,
            "ghl_contact_id": ghl_contact_id,
            "ghl_opportunity_id": opportunity_id,
            "loyalty_points": self.ghl.loyalty_points(customer),
            "tags": sorted(tags),
            "customer_id": customer.id,
            "order_id": order.id if order else None,
        }

    async def _record_product_interests(
        self,
        customer_id: str,
        items: list[Any],
        *,
        source: str,
    ) -> None:
        for item in items:
            await self.product_interests.record_interest(
                customer_id=customer_id,
                product_id=item.product_id,
                sku=item.sku,
                product_name=item.name,
                source=source,
            )

    async def _process_product_stock(self, normalized: NormalizedEvent) -> dict[str, Any]:
        product_stock = normalized.product_stock
        if not product_stock:
            return {"ignored": True, "reason": "missing_product_stock"}

        if product_stock.in_stock is not True:
            return {
                "ignored": False,
                "reason": "product_not_back_in_stock",
                "product_id": product_stock.product_id,
                "sku": product_stock.sku,
            }

        interested_customers = await self.product_interests.interested_customers(
            product_id=product_stock.product_id,
            sku=product_stock.sku,
        )
        notified = 0
        for customer, interest in interested_customers:
            tags = {tag.tag for tag in customer.tags if tag.active}
            tags.update(self._event_tags(normalized))
            product_tag = normalize_tag(product_stock.sku or product_stock.name or interest.product_name)
            if product_tag:
                tags.add(f"salla-back-in-stock-{product_tag}"[:50])
            await self.customers.sync_tags(customer, tags)
            ghl_contact_id = await self.ghl.sync_contact(customer, None, tags)
            await self.customers.set_ghl_contact_id(customer, ghl_contact_id)
            await self.product_interests.mark_notified(interest)
            notified += 1

        return {
            "sent_to_ghl": notified > 0,
            "notified_customers": notified,
            "product_id": product_stock.product_id,
            "sku": product_stock.sku,
        }

    def _event_tags(self, normalized: NormalizedEvent) -> set[str]:
        tags = {"salla"}
        event_tag = normalize_tag(normalized.event_type)
        if event_tag:
            tags.add(f"salla-event-{event_tag}")

        if normalized.event_type.startswith("customer."):
            tags.add("salla-customer")
            if normalized.event_type in {"customer.created", "customer.registered"}:
                tags.add("salla-customer-created")
                tags.add("salla-welcome-campaign")

        if normalized.order:
            if "status" in normalized.event_type or normalized.event_type in {
                "order.updated",
                "order.cancelled",
                "order.canceled",
                "order.refunded",
            }:
                tags.add("salla-order-status-updated")
                tags.add("salla-shipping-update")
            if self._is_cancel_or_refund(normalized):
                tags.add("salla-stop-cross-sell")

        if normalized.cart:
            tags.add("salla-cart-abandoned")
            for item in normalized.cart.items:
                product_tag = normalize_tag(item.sku or item.name)
                if product_tag:
                    tags.add(f"salla-cart-product-{product_tag}"[:50])

        if normalized.product_stock:
            tags.add("salla-product-stock-updated")
            if normalized.product_stock.in_stock:
                tags.add("salla-back-in-stock")
            product_tag = normalize_tag(normalized.product_stock.sku or normalized.product_stock.name)
            if product_tag:
                tags.add(f"salla-stock-product-{product_tag}"[:50])

        return tags

    def _is_cancel_or_refund(self, normalized: NormalizedEvent) -> bool:
        event_type = normalized.event_type
        status = (normalized.order.status if normalized.order else None) or ""
        normalized_status = normalize_tag(status)
        return event_type in {"order.cancelled", "order.canceled", "order.refunded"} or normalized_status in {
            "cancelled",
            "canceled",
            "refunded",
        }
