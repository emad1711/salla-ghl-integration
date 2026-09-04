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
            self.call_order: list[str] = []

        async def sync_contact(self, customer, order, tags: set[str]) -> str:
            self.call_order.append("sync_contact")
            self.synced_tags = tags
            return "ghl-contact-1"

        async def trigger_abandoned_checkout_webhook(self, *, customer, cart, contact_id, tags):
            self.call_order.append("trigger_abandoned_checkout_webhook")
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
    assert fake_ghl.call_order == ["sync_contact", "trigger_abandoned_checkout_webhook"]
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
    flow_messages = [
        record.getMessage() for record in caplog.records if "[ABANDONED_CART_DIAGNOSTIC]" in record.getMessage()
    ]
    assert "[ABANDONED_CART_DIAGNOSTIC] abandoned.cart received" in flow_messages
    assert all("buyer@example.com" not in message for message in flow_messages)
    assert all("0500000000" not in message for message in flow_messages)
    assert all("https://store.test/checkout/cart-1" not in message for message in flow_messages)
    assert all("cart-1" not in message for message in flow_messages if "abandoned.cart received" in message)


async def _process_with_fake_ghl(normalized, fake_ghl):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        service = EventService(session)
        service.ghl = fake_ghl  # type: ignore[assignment]
        return await service._process_normalized(normalized)


def _flow_messages(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if "[ABANDONED_CART_DIAGNOSTIC]" in record.getMessage()]


async def test_abandoned_cart_flow_logs_upsert_failed_when_contact_id_missing(caplog) -> None:
    caplog.set_level(logging.WARNING)

    class FakeGHL:
        async def sync_contact(self, customer, order, tags: set[str]) -> None:
            return None

        async def trigger_abandoned_checkout_webhook(self, *, customer, cart, contact_id, tags):
            return {"sent": False, "reason": "missing_contact_id"}

        def loyalty_points(self, customer) -> int:
            return 0

    result = await _process_with_fake_ghl(_abandoned_cart_event("abandoned.cart"), FakeGHL())
    messages = _flow_messages(caplog)

    assert result["ghl_contact_id"] is None
    assert "[ABANDONED_CART_DIAGNOSTIC] GHL upsert: FAILED" in messages
    assert "[ABANDONED_CART_DIAGNOSTIC] GHL inbound webhook: FAILED" in messages
    assert "[ABANDONED_CART_DIAGNOSTIC] GHL upsert: SUCCESS" not in messages
    assert all("buyer@example.com" not in message for message in messages)
    assert all("0500000000" not in message for message in messages)


async def test_abandoned_cart_flow_logs_upsert_failed_on_exception(caplog) -> None:
    caplog.set_level(logging.WARNING)

    class FakeGHL:
        async def sync_contact(self, customer, order, tags: set[str]) -> str:
            raise RuntimeError("ghl upsert unavailable")

        async def trigger_abandoned_checkout_webhook(self, *, customer, cart, contact_id, tags):
            raise AssertionError("inbound webhook must not run after upsert failure")

        def loyalty_points(self, customer) -> int:
            return 0

    try:
        await _process_with_fake_ghl(_abandoned_cart_event("abandoned.cart"), FakeGHL())
    except RuntimeError as exc:
        assert str(exc) == "ghl upsert unavailable"
    else:
        raise AssertionError("upsert exception must propagate")

    messages = _flow_messages(caplog)
    assert any(message == "[ABANDONED_CART_DIAGNOSTIC] GHL upsert: FAILED" for message in messages)
    assert all("GHL inbound webhook" not in message for message in messages)
    assert all("buyer@example.com" not in message for message in messages)
    assert all("Authorization" not in message for message in messages)
    assert any(record.exc_text and "ghl upsert unavailable" in record.exc_text for record in caplog.records)


async def test_abandoned_cart_flow_logs_inbound_webhook_failed_on_exception(caplog) -> None:
    caplog.set_level(logging.WARNING)

    class FakeGHL:
        async def sync_contact(self, customer, order, tags: set[str]) -> str:
            return "ghl-contact-1"

        async def trigger_abandoned_checkout_webhook(self, *, customer, cart, contact_id, tags):
            raise RuntimeError("ghl inbound webhook unavailable")

        def loyalty_points(self, customer) -> int:
            return 0

    try:
        await _process_with_fake_ghl(_abandoned_cart_event("abandoned.cart"), FakeGHL())
    except RuntimeError as exc:
        assert str(exc) == "ghl inbound webhook unavailable"
    else:
        raise AssertionError("inbound webhook exception must propagate")

    messages = _flow_messages(caplog)
    assert "[ABANDONED_CART_DIAGNOSTIC] GHL upsert: SUCCESS" in messages
    assert any(message == "[ABANDONED_CART_DIAGNOSTIC] GHL inbound webhook: FAILED" for message in messages)
    assert all("buyer@example.com" not in message for message in messages)
    assert all("https://store.test/checkout/cart-1" not in message for message in messages)
    assert any(record.exc_text and "ghl inbound webhook unavailable" in record.exc_text for record in caplog.records)


async def test_order_created_does_not_emit_abandoned_cart_flow_checkpoints(caplog) -> None:
    caplog.set_level(logging.WARNING)

    class FakeGHL:
        async def sync_contact(self, customer, order, tags: set[str]) -> str:
            return "ghl-contact-1"

        async def trigger_abandoned_checkout_webhook(self, *, customer, cart, contact_id, tags):
            raise AssertionError("order.created must not send abandoned checkout webhook")

        def loyalty_points(self, customer) -> int:
            return 0

    event = _abandoned_cart_event("order.created")
    event = NormalizedEvent(
        event_type="order.created",
        merchant_id=event.merchant_id,
        event_id=event.event_id,
        customer=event.customer,
        order=None,
        cart=None,
        product_stock=None,
        raw_payload={},
    )
    await _process_with_fake_ghl(event, FakeGHL())
    assert _flow_messages(caplog) == []
