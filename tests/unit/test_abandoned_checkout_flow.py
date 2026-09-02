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

    normalized = NormalizedEvent(
        event_type="cart.abandoned",
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
        await service.receive(json.dumps(payload).encode("utf-8"))

    diagnostic_messages = [
        record.getMessage() for record in caplog.records if "SALLA_CART_ABANDONED_DIAGNOSTIC" in record.getMessage()
    ]
    assert diagnostic_messages
    assert '"event": "abandoned.cart"' in diagnostic_messages[0]
    assert '"path": "id"' in diagnostic_messages[0]
    assert "buyer@example.com" not in diagnostic_messages[0]
    assert "0500000000" not in diagnostic_messages[0]
