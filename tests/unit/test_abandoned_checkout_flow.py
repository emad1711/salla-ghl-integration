import json
import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from salla_ghl.core.config import settings
from salla_ghl.db.models import Base
from salla_ghl.integrations.salla.normalizer import (
    NormalizedCart,
    NormalizedCustomer,
    NormalizedEvent,
    NormalizedOrderItem,
)
from salla_ghl.services.event_service import EventService, _is_abandoned_cart_diagnostic_event


def test_abandoned_cart_diagnostic_condition_covers_documented_event() -> None:
    assert _is_abandoned_cart_diagnostic_event("abandoned.cart") is True
    assert _is_abandoned_cart_diagnostic_event("cart.abandoned") is True
    assert _is_abandoned_cart_diagnostic_event("abandoned_cart") is True
    assert _is_abandoned_cart_diagnostic_event("order.created") is False
    assert _is_abandoned_cart_diagnostic_event("abandoned.cart.created") is False
    assert _is_abandoned_cart_diagnostic_event(None) is False
    assert "abandoned.cart" in settings.salla_allowed_events
    assert settings.ghl_abandoned_checkout_webhook_url == ""


def _abandoned_cart_event(event_type: str) -> NormalizedEvent:
    return NormalizedEvent(
        event_type=event_type,
        merchant_id="merchant-1",
        event_id="event-1",
        customer=NormalizedCustomer(
            salla_customer_id="salla-customer-1",
            first_name="Buyer",
            last_name="Test",
            name="Buyer Test",
            email="buyer@example.com",
            phone="0500000000",
        ),
        order=None,
        cart=NormalizedCart(
            salla_cart_id="cart-1",
            checkout_url="https://store.test/checkout/cart-1",
            total_amount=Decimal("120"),
            currency="SAR",
            items=[
                NormalizedOrderItem(
                    product_id="product-1",
                    sku="SKU-1",
                    name="Product 1",
                    quantity=1,
                    unit_price=Decimal("120"),
                    total_price=Decimal("120"),
                )
            ],
        ),
        product_stock=None,
        raw_payload={},
    )


async def test_cart_abandoned_reaches_ghl_webhook_sender_after_contact_upsert(caplog) -> None:
    caplog.set_level(logging.WARNING)

    class FakeGHL:
        def __init__(self) -> None:
            self.synced_tags: set[str] | None = None
            self.trigger_calls: list[dict[str, object]] = []

        async def sync_contact(self, customer, order, tags: set[str]) -> str:
            self.synced_tags = tags
            return "ghl-contact-1"

        async def trigger_abandoned_checkout_webhook(self, *, customer, cart, contact_id, tags):
            self.trigger_calls.append(
                {
                    "customer": customer,
                    "cart": cart,
                    "contact_id": contact_id,
                    "tags": tags,
                }
            )
            return {"sent": True}

        def loyalty_points(self, customer) -> int:
            return 0

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    normalized = _abandoned_cart_event("cart.abandoned")

    async with session_factory() as session:
        service = EventService(session)
        fake_ghl = FakeGHL()
        service.ghl = fake_ghl  # type: ignore[assignment]

        result = await service._process_normalized(normalized)

    assert result["ghl_contact_id"] == "ghl-contact-1"
    assert fake_ghl.synced_tags is not None
    assert "salla-cart-abandoned" in fake_ghl.synced_tags
    assert "salla-event-cart-abandoned" in fake_ghl.synced_tags
    assert len(fake_ghl.trigger_calls) == 1
    assert fake_ghl.trigger_calls[0]["contact_id"] == "ghl-contact-1"
    assert fake_ghl.trigger_calls[0]["cart"].checkout_url == "https://store.test/checkout/cart-1"
    assert any("SALLA_CART_ABANDONED_PROCESSING_DIAGNOSTIC" in record.getMessage() for record in caplog.records)
    flow_messages = [record.getMessage() for record in caplog.records if "[ABANDONED_CART_DIAGNOSTIC]" in record.getMessage()]
    assert "[ABANDONED_CART_DIAGNOSTIC] GHL upsert: SUCCESS" in flow_messages
    assert "[ABANDONED_CART_DIAGNOSTIC] GHL inbound webhook: SUCCESS" in flow_messages
    assert all("buyer@example.com" not in message for message in flow_messages)
    assert all("0500000000" not in message for message in flow_messages)
    assert all("https://store.test/checkout/cart-1" not in message for message in flow_messages)


async def test_documented_abandoned_cart_applies_tags_and_upserts_contact(caplog) -> None:
    caplog.set_level(logging.WARNING)

    class FakeGHL:
        def __init__(self) -> None:
            self.synced_tags: set[str] | None = None
            self.trigger_calls: list[dict[str, object]] = []

        async def sync_contact(self, customer, order, tags: set[str]) -> str:
            self.synced_tags = tags
            return "ghl-contact-1"

        async def trigger_abandoned_checkout_webhook(self, *, customer, cart, contact_id, tags):
            self.trigger_calls.append(
                {
                    "customer": customer,
                    "cart": cart,
                    "contact_id": contact_id,
                    "tags": tags,
                }
            )
            return {"sent": False, "reason": "missing_webhook_url"}

        def loyalty_points(self, customer) -> int:
            return 0

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        service = EventService(session)
        fake_ghl = FakeGHL()
        service.ghl = fake_ghl  # type: ignore[assignment]
        result = await service._process_normalized(_abandoned_cart_event("abandoned.cart"))

    processing_messages = [
        record.getMessage()
        for record in caplog.records
        if "SALLA_CART_ABANDONED_PROCESSING_DIAGNOSTIC" in record.getMessage()
    ]
    assert result["ghl_contact_id"] == "ghl-contact-1"
    assert result["abandoned_checkout_event"] == {"sent": False, "reason": "missing_webhook_url"}
    assert fake_ghl.synced_tags is not None
    assert "salla-cart-abandoned" in fake_ghl.synced_tags
    assert "salla-event-abandoned-cart" in fake_ghl.synced_tags
    assert len(fake_ghl.trigger_calls) == 1
    assert processing_messages
    assert '"event": "abandoned.cart"' in processing_messages[0]
    assert '"request_received": true' in processing_messages[0]
    assert '"normalized_event_type": "abandoned.cart"' in processing_messages[0]
    assert '"ghl_contact_upsert_succeeded": true' in processing_messages[0]
    assert '"salla-cart-abandoned": true' in processing_messages[0]
    assert "buyer@example.com" not in processing_messages[0]
    assert "0500000000" not in processing_messages[0]
    flow_messages = [record.getMessage() for record in caplog.records if "[ABANDONED_CART_DIAGNOSTIC]" in record.getMessage()]
    assert "[ABANDONED_CART_DIAGNOSTIC] GHL upsert: SUCCESS" in flow_messages
    assert "[ABANDONED_CART_DIAGNOSTIC] GHL inbound webhook: FAILED" in flow_messages
    assert all("buyer@example.com" not in message for message in flow_messages)
    assert all("0500000000" not in message for message in flow_messages)


async def test_receive_logs_diagnostic_for_documented_abandoned_cart_event(caplog) -> None:
    caplog.set_level(logging.WARNING)
    assert _is_abandoned_cart_diagnostic_event("abandoned.cart") is True
    assert "abandoned.cart" in settings.salla_allowed_events

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    payload = {
        "event": "abandoned.cart",
        "merchant": "merchant-1",
        "data": {
            "id": "cart-1",
            "checkout_url": "https://store.test/checkout/cart-1",
            "total": {"amount": 120, "currency": "SAR"},
            "items": [{"id": "product-1", "sku": "SKU-1", "quantity": 1, "price": {"amount": 120}}],
            "customer": {"id": "salla-customer-1", "email": "buyer@example.com", "mobile": "0500000000"},
        },
    }

    async with session_factory() as session:
        service = EventService(session)
        event_id, created, status = await service.receive(json.dumps(payload).encode("utf-8"))

    assert created is True
    assert status == "queued"
    assert event_id

    diagnostic_messages = [
        record.getMessage() for record in caplog.records if "SALLA_CART_ABANDONED_DIAGNOSTIC" in record.getMessage()
    ]
    assert diagnostic_messages
    assert '"event": "abandoned.cart"' in diagnostic_messages[0]
    assert '"request_received": true' in diagnostic_messages[0]
    assert '"normalized_event_type": "abandoned.cart"' in diagnostic_messages[0]
    assert '"salla_customer_id": "salla-customer-1"' in diagnostic_messages[0]
    assert '"allowed_event": true' in diagnostic_messages[0]
    assert '"path": "id"' in diagnostic_messages[0]
    assert "buyer@example.com" not in diagnostic_messages[0]
    assert "0500000000" not in diagnostic_messages[0]
