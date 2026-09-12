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
    SallaNormalizer,
)
from salla_ghl.services.event_service import EventService, _is_abandoned_cart_diagnostic_event, _is_purchase_event


def test_purchase_event_detection_uses_official_salla_name() -> None:
    assert _is_purchase_event("abandoned.cart.purchased") is True
    assert _is_purchase_event("abandoned_cart.purchased") is True
    assert _is_purchase_event("abandoned.cart") is False
    assert _is_purchase_event("cart.abandoned") is False
    assert _is_purchase_event("order.created") is False
    assert _is_purchase_event("abandoned.cart.status.changed") is False
    assert _is_purchase_event(None) is False
    assert _is_abandoned_cart_diagnostic_event("abandoned.cart.purchased") is False
    assert "abandoned.cart.purchased" in settings.salla_allowed_events
    assert settings.ghl_purchase_webhook_url == ""


def _purchase_event(
    *,
    event_type: str = "abandoned.cart.purchased",
    checkout_url: str | None = "https://store.test/checkout/cart-1",
    include_customer: bool = True,
    raw_payload: dict | None = None,
) -> NormalizedEvent:
    customer = None
    if include_customer:
        customer = NormalizedCustomer(
            salla_customer_id="salla-customer-1",
            first_name="Buyer",
            last_name="Test",
            name="Buyer Test",
            email="buyer@example.com",
            phone="0500000000",
        )
    return NormalizedEvent(
        event_type=event_type,
        merchant_id="merchant-1",
        event_id="event-1",
        customer=customer,
        order=None,
        cart=NormalizedCart(
            salla_cart_id="cart-1",
            checkout_url=checkout_url,
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
        raw_payload=raw_payload
        or {
            "event": event_type,
            "data": {
                "id": "cart-1",
                "status": "purchased",
                **({"checkout_url": checkout_url} if checkout_url else {}),
                "order_id": "order-9",
            },
        },
    )


class FakePurchaseGHL:
    def __init__(self, *, contact_id: str | None = "ghl-contact-1", webhook_result=None, fail_webhook: Exception | None = None) -> None:
        self.synced_tags: set[str] | None = None
        self.abandoned_calls: list[dict[str, object]] = []
        self.purchase_calls: list[dict[str, object]] = []
        self.call_order: list[str] = []
        self.contact_id = contact_id
        self.webhook_result = webhook_result if webhook_result is not None else {"sent": True}
        self.fail_webhook = fail_webhook

    async def sync_contact(self, customer, order, tags: set[str]) -> str | None:
        self.call_order.append("sync_contact")
        self.synced_tags = tags
        return self.contact_id

    async def trigger_abandoned_checkout_webhook(self, *, customer, cart, contact_id, tags):
        self.call_order.append("trigger_abandoned_checkout_webhook")
        self.abandoned_calls.append({"contact_id": contact_id, "cart": cart, "tags": tags})
        raise AssertionError("purchase must not send abandoned checkout webhook")

    async def trigger_purchase_webhook(self, *, customer, contact_id, tags, event_type, cart, order_id):
        self.call_order.append("trigger_purchase_webhook")
        self.purchase_calls.append(
            {
                "customer": customer,
                "contact_id": contact_id,
                "tags": tags,
                "event_type": event_type,
                "cart": cart,
                "order_id": order_id,
            }
        )
        if self.fail_webhook:
            raise self.fail_webhook
        return self.webhook_result

    def loyalty_points(self, customer) -> int:
        return 0


async def _process(normalized, fake_ghl):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        service = EventService(session)
        service.ghl = fake_ghl  # type: ignore[assignment]
        return await service._process_normalized(normalized)


async def test_purchase_upserts_contact_and_sends_ghl_purchase_trigger(caplog) -> None:
    caplog.set_level(logging.WARNING)
    fake_ghl = FakePurchaseGHL()
    result = await _process(_purchase_event(), fake_ghl)

    assert result["ghl_contact_id"] == "ghl-contact-1"
    assert result["purchase_event"] == {"sent": True}
    assert result["abandoned_checkout_event"] is None
    assert fake_ghl.call_order == ["sync_contact", "trigger_purchase_webhook"]
    assert fake_ghl.abandoned_calls == []
    assert len(fake_ghl.purchase_calls) == 1
    assert fake_ghl.purchase_calls[0]["event_type"] == "abandoned.cart.purchased"
    assert fake_ghl.purchase_calls[0]["contact_id"] == "ghl-contact-1"
    assert fake_ghl.purchase_calls[0]["order_id"] == "order-9"
    assert fake_ghl.purchase_calls[0]["cart"].checkout_url == "https://store.test/checkout/cart-1"
    assert fake_ghl.synced_tags is not None
    assert "salla-cart-purchased" in fake_ghl.synced_tags
    assert "salla-event-abandoned-cart-purchased" in fake_ghl.synced_tags
    assert "salla-cart-abandoned" not in fake_ghl.synced_tags
    received = [record.getMessage() for record in caplog.records if "SALLA_PURCHASE_EVENT" in record.getMessage()]
    assert received
    assert '"detected_event_name": "abandoned.cart.purchased"' in received[0]
    assert "buyer@example.com" not in received[0]
    assert "0500000000" not in received[0]


async def test_purchase_omits_checkout_url_when_salla_did_not_send_it() -> None:
    fake_ghl = FakePurchaseGHL()
    await _process(_purchase_event(checkout_url=None), fake_ghl)

    assert fake_ghl.purchase_calls[0]["cart"].checkout_url is None


async def test_purchase_missing_customer_is_ignored(caplog) -> None:
    caplog.set_level(logging.WARNING)
    fake_ghl = FakePurchaseGHL()
    result = await _process(_purchase_event(include_customer=False), fake_ghl)

    assert result == {"ignored": True, "reason": "missing_customer"}
    assert fake_ghl.call_order == []
    ignored = [record.getMessage() for record in caplog.records if "SALLA_PURCHASE_EVENT" in record.getMessage()]
    assert any('"reason": "missing_customer"' in message for message in ignored)


async def test_purchase_looks_up_customer_from_previous_abandoned_cart() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from salla_ghl.db.models import Customer

    async with session_factory() as session:
        service = EventService(session)
        fake_ghl = FakePurchaseGHL()
        service.ghl = fake_ghl  # type: ignore[assignment]
        customer = Customer(
            salla_customer_id="salla-customer-1",
            email="buyer@example.com",
            phone="0500000000",
            first_name="Buyer",
            last_name="Test",
        )
        session.add(customer)
        await session.flush()
        await service.workflow_engine.schedule_abandoned_cart(customer, "cart-1")
        result = await service._process_normalized(_purchase_event(include_customer=False))

    assert result["ghl_contact_id"] == "ghl-contact-1"
    assert fake_ghl.call_order == ["sync_contact", "trigger_purchase_webhook"]
    assert fake_ghl.purchase_calls[0]["event_type"] == "abandoned.cart.purchased"


async def test_receive_logs_official_purchase_event(caplog) -> None:
    caplog.set_level(logging.WARNING)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    payload = {
        "event": "abandoned.cart.purchased",
        "merchant": "merchant-1",
        "data": {
            "id": "cart-1",
            "status": "purchased",
            "checkout_url": "https://store.test/checkout/cart-1",
            "total": {"amount": 120, "currency": "SAR"},
            "customer": {"id": "salla-customer-1", "email": "buyer@example.com", "mobile": "0500000000"},
        },
    }

    async with session_factory() as session:
        service = EventService(session)
        event_id, created, status = await service.receive(json.dumps(payload).encode("utf-8"))

    assert created is True
    assert status == "queued"
    assert event_id
    messages = [record.getMessage() for record in caplog.records if "SALLA_PURCHASE_EVENT" in record.getMessage()]
    assert messages
    assert '"event": "abandoned.cart.purchased"' in messages[0]
    assert '"detected_event_name": "abandoned.cart.purchased"' in messages[0]
    assert '"value": "cart-1"' in messages[0]
    assert '"value": "https://store.test/checkout/cart-1"' in messages[0]
    assert "buyer@example.com" not in messages[0]
    assert "0500000000" not in messages[0]
    assert all("[ABANDONED_CART_DIAGNOSTIC]" not in record.getMessage() for record in caplog.records)


async def test_purchase_webhook_failure_is_logged_and_raised(caplog) -> None:
    caplog.set_level(logging.ERROR)
    fake_ghl = FakePurchaseGHL(fail_webhook=RuntimeError("ghl purchase webhook unavailable"))
    try:
        await _process(_purchase_event(), fake_ghl)
    except RuntimeError as exc:
        assert str(exc) == "ghl purchase webhook unavailable"
    else:
        raise AssertionError("purchase webhook exception must propagate")

    failed = [record.getMessage() for record in caplog.records if "SALLA_PURCHASE_GHL_TRIGGER" in record.getMessage()]
    assert failed
    assert '"success": false' in failed[0]
    assert '"event": "abandoned.cart.purchased"' in failed[0]
    assert "Authorization" not in "".join(record.getMessage() for record in caplog.records)


def test_normalizer_preserves_official_checkout_url_exactly() -> None:
    official_url = "https://salla.sa/dev-wofftr4xsra5xtlv/checkout/1097962121"
    normalized = SallaNormalizer().normalize(
        {
            "event": "abandoned.cart.purchased",
            "data": {"id": 1097962121, "checkout_url": official_url, "total": {"amount": 100, "currency": "SAR"}},
        }
    )
    assert normalized.cart is not None
    assert normalized.cart.checkout_url == official_url
