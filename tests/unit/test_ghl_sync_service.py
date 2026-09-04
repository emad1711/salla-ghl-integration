import logging
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from salla_ghl.core.config import settings
from salla_ghl.db.models import Base, Customer, Order
from salla_ghl.integrations.ghl.client import GHLClient, GHLClientError
from salla_ghl.integrations.salla.normalizer import NormalizedCart, NormalizedOrderItem
from salla_ghl.services.ghl_sync_service import GHLSyncService


def test_loyalty_points_are_calculated_from_spend_and_order_bonus() -> None:
    old_per_unit = settings.loyalty_points_per_currency_unit
    old_per_order = settings.loyalty_points_per_order
    object.__setattr__(settings, "loyalty_points_per_currency_unit", 2)
    object.__setattr__(settings, "loyalty_points_per_order", 10)
    customer = Customer(total_spent=Decimal("125.50"), purchase_count=3)

    try:
        points = GHLSyncService(None).loyalty_points(customer)  # type: ignore[arg-type]
    finally:
        object.__setattr__(settings, "loyalty_points_per_currency_unit", old_per_unit)
        object.__setattr__(settings, "loyalty_points_per_order", old_per_order)

    assert points == 281


def test_builds_order_opportunity_payload() -> None:
    old_pipeline_id = settings.ghl_pipeline_id
    old_stage_id = settings.ghl_pipeline_stage_id
    old_location_id = settings.ghl_location_id
    object.__setattr__(settings, "ghl_pipeline_id", "pipeline-1")
    object.__setattr__(settings, "ghl_pipeline_stage_id", "stage-1")
    object.__setattr__(settings, "ghl_location_id", "location-1")

    customer = Customer(ghl_contact_id="contact-1")
    order = Order(salla_order_id="123", reference_id="ORD-123", total_amount=Decimal("250.00"))

    try:
        payload = GHLSyncService(None)._build_opportunity_payload(customer, order)  # type: ignore[arg-type]
    finally:
        object.__setattr__(settings, "ghl_pipeline_id", old_pipeline_id)
        object.__setattr__(settings, "ghl_pipeline_stage_id", old_stage_id)
        object.__setattr__(settings, "ghl_location_id", old_location_id)

    assert payload["locationId"] == "location-1"
    assert payload["pipelineId"] == "pipeline-1"
    assert payload["pipelineStageId"] == "stage-1"
    assert payload["contactId"] == "contact-1"
    assert payload["name"] == "Salla Order ORD-123"
    assert payload["monetaryValue"] == 250.0


def test_contact_payload_phone_is_always_string_when_present() -> None:
    numeric_customer = Customer(phone=966500000000)  # type: ignore[arg-type]
    leading_zero_customer = Customer(phone="0500000000")

    numeric_payload = GHLSyncService(None)._build_contact_payload(numeric_customer, None, set())  # type: ignore[arg-type]
    leading_zero_payload = GHLSyncService(None)._build_contact_payload(
        leading_zero_customer,
        None,
        set(),
    )  # type: ignore[arg-type]

    assert numeric_payload["phone"] == "966500000000"
    assert isinstance(numeric_payload["phone"], str)
    assert leading_zero_payload["phone"] == "0500000000"


def test_contact_payload_omits_empty_phone() -> None:
    customer = Customer(phone=None)

    payload = GHLSyncService(None)._build_contact_payload(customer, None, set())  # type: ignore[arg-type]

    assert "phone" not in payload


def test_builds_abandoned_checkout_payload_with_real_cart_values() -> None:
    old_location_id = settings.ghl_location_id
    object.__setattr__(settings, "ghl_location_id", "location-1")
    customer = Customer(
        salla_customer_id="salla-customer-1",
        email="buyer@example.com",
        phone="0500000000",
        first_name="Buyer",
        last_name="Test",
    )
    cart = NormalizedCart(
        salla_cart_id="cart-1",
        checkout_url="https://store.test/checkout/cart-1",
        total_amount=Decimal("250.50"),
        currency="SAR",
        items=[
            NormalizedOrderItem(
                product_id="product-1",
                sku="SKU-1",
                name="Product 1",
                quantity=2,
                unit_price=Decimal("100.25"),
                total_price=Decimal("200.50"),
            )
        ],
    )

    try:
        payload = GHLSyncService(None)._build_abandoned_checkout_payload(  # type: ignore[arg-type]
            customer=customer,
            cart=cart,
            contact_id="ghl-contact-1",
            tags={"salla-cart-abandoned"},
        )
    finally:
        object.__setattr__(settings, "ghl_location_id", old_location_id)

    assert payload["event"] == "abandoned.cart"
    assert payload["eventTimestamp"]
    assert payload["contactId"] == "ghl-contact-1"
    assert payload["email"] == "buyer@example.com"
    assert payload["phone"] == "0500000000"
    assert payload["sallaCustomerId"] == "salla-customer-1"
    assert payload["sallaCartId"] == "cart-1"
    assert payload["checkoutUrl"] == "https://store.test/checkout/cart-1"
    assert payload["cartTotal"] == 250.5
    assert payload["currency"] == "SAR"
    assert payload["customer"]["phone"] == "0500000000"
    assert payload["items"][0]["sku"] == "SKU-1"
    assert payload["tags"] == ["salla-cart-abandoned"]
    assert payload["event"] != "abandoned.cart.created"


async def test_abandoned_checkout_webhook_is_skipped_when_url_is_empty(caplog) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def post_inbound_webhook(self, webhook_url: str, payload: dict[str, object]) -> dict[str, object]:
            self.calls.append({"webhook_url": webhook_url, "payload": payload})
            return {"status_code": 200, "body": {"ok": True}}

    caplog.set_level(logging.WARNING)
    old_webhook_url = settings.ghl_abandoned_checkout_webhook_url
    object.__setattr__(settings, "ghl_abandoned_checkout_webhook_url", "")

    customer = Customer(salla_customer_id="salla-customer-1", email="buyer@example.com", phone="0500000000")
    cart = NormalizedCart(
        salla_cart_id="cart-1",
        checkout_url="https://store.test/checkout/cart-1",
        total_amount=Decimal("100"),
        currency="SAR",
        items=[],
    )

    try:
        service = GHLSyncService(None)  # type: ignore[arg-type]
        fake_client = FakeClient()
        service.client = fake_client  # type: ignore[assignment]

        result = await service.trigger_abandoned_checkout_webhook(
            customer=customer,
            cart=cart,
            contact_id="ghl-contact-1",
            tags={"salla-cart-abandoned"},
        )
    finally:
        object.__setattr__(settings, "ghl_abandoned_checkout_webhook_url", old_webhook_url)

    assert result == {"sent": False, "reason": "missing_webhook_url"}
    assert fake_client.calls == []
    skip_logs = [record.getMessage() for record in caplog.records if "GHL inbound webhook skipped" in record.getMessage()]
    assert skip_logs
    assert '"reason": "missing_webhook_url"' in skip_logs[0]
    assert "buyer@example.com" not in skip_logs[0]
    assert "0500000000" not in skip_logs[0]


async def test_abandoned_checkout_webhook_is_not_sent_twice_for_same_cart() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def post_inbound_webhook(self, webhook_url: str, payload: dict[str, object]) -> dict[str, object]:
            self.calls.append({"webhook_url": webhook_url, "payload": payload})
            return {"status_code": 200, "body": {"ok": True}}

    old_location_id = settings.ghl_location_id
    old_webhook_url = settings.ghl_abandoned_checkout_webhook_url
    object.__setattr__(settings, "ghl_location_id", "location-1")
    object.__setattr__(settings, "ghl_abandoned_checkout_webhook_url", "https://example.test/webhook")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    customer = Customer(salla_customer_id="salla-customer-1", email="buyer@example.com", phone="0500000000")
    cart = NormalizedCart(
        salla_cart_id="cart-1",
        checkout_url="https://store.test/checkout/cart-1",
        total_amount=Decimal("100"),
        currency="SAR",
        items=[],
    )

    try:
        async with session_factory() as session:
            service = GHLSyncService(session)
            fake_client = FakeClient()
            service.client = fake_client  # type: ignore[assignment]

            first = await service.trigger_abandoned_checkout_webhook(
                customer=customer,
                cart=cart,
                contact_id="ghl-contact-1",
                tags={"salla-cart-abandoned"},
            )
            second = await service.trigger_abandoned_checkout_webhook(
                customer=customer,
                cart=cart,
                contact_id="ghl-contact-1",
                tags={"salla-cart-abandoned"},
            )

        assert first["sent"] is True
        assert second["sent"] is False
        assert second["reason"] == "duplicate"
        assert len(fake_client.calls) == 1
        assert fake_client.calls[0]["payload"]["contactId"] == "ghl-contact-1"  # type: ignore[index]
        assert fake_client.calls[0]["payload"]["event"] == "abandoned.cart"  # type: ignore[index]
        assert "/events" not in str(fake_client.calls[0]["webhook_url"])
        assert "workflows-marketplace/triggers/execute" not in str(fake_client.calls[0]["webhook_url"])
    finally:
        object.__setattr__(settings, "ghl_location_id", old_location_id)
        object.__setattr__(settings, "ghl_abandoned_checkout_webhook_url", old_webhook_url)


async def test_abandoned_checkout_webhook_payload_includes_required_fields() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        async def post_inbound_webhook(self, webhook_url: str, payload: dict[str, object]) -> dict[str, object]:
            self.payloads.append(payload)
            return {"status_code": 201, "body": {"ok": True}}

    old_location_id = settings.ghl_location_id
    old_webhook_url = settings.ghl_abandoned_checkout_webhook_url
    object.__setattr__(settings, "ghl_location_id", "location-1")
    object.__setattr__(settings, "ghl_abandoned_checkout_webhook_url", "https://example.test/webhook")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    customer = Customer(
        salla_customer_id="salla-customer-1",
        email="buyer@example.com",
        phone="0500000000",
        first_name="Buyer",
        last_name="Test",
    )
    cart = NormalizedCart(
        salla_cart_id="cart-1",
        checkout_url="https://store.test/checkout/cart-1",
        total_amount=Decimal("100"),
        currency="SAR",
        items=[],
    )

    try:
        async with session_factory() as session:
            service = GHLSyncService(session)
            fake_client = FakeClient()
            service.client = fake_client  # type: ignore[assignment]
            result = await service.trigger_abandoned_checkout_webhook(
                customer=customer,
                cart=cart,
                contact_id="ghl-contact-1",
                tags={"salla-cart-abandoned"},
            )
    finally:
        object.__setattr__(settings, "ghl_location_id", old_location_id)
        object.__setattr__(settings, "ghl_abandoned_checkout_webhook_url", old_webhook_url)

    assert result["sent"] is True
    payload = fake_client.payloads[0]
    assert payload["event"] == "abandoned.cart"
    assert payload["contactId"] == "ghl-contact-1"
    assert payload["email"] == "buyer@example.com"
    assert payload["phone"] == "0500000000"
    assert payload["checkoutUrl"] == "https://store.test/checkout/cart-1"
    assert payload["locationId"] == "location-1"
    assert payload["sallaCustomerId"] == "salla-customer-1"
    assert payload["sallaCartId"] == "cart-1"


async def test_inbound_webhook_logs_start_and_treats_2xx_as_success(caplog) -> None:
    caplog.set_level(logging.WARNING)

    class FakeResponse:
        status_code = 201
        text = '{"ok": true}'

        def json(self) -> dict[str, object]:
            return {"ok": True}

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, headers: dict[str, str] | None = None, json: dict[str, object] | None = None):
            assert url == "https://example.test/webhook"
            assert headers == {"Accept": "application/json", "Content-Type": "application/json"}
            assert json is not None
            assert json["event"] == "abandoned.cart"
            return FakeResponse()

    payload = {
        "event": "abandoned.cart",
        "contactId": "ghl-contact-99",
        "locationId": "location-1",
        "email": "buyer@example.com",
        "phone": "0500000000",
        "checkoutUrl": "https://store.test/checkout/cart-1",
    }

    with patch("salla_ghl.integrations.ghl.client.httpx.AsyncClient", FakeAsyncClient):
        result = await GHLClient(None).post_inbound_webhook(  # type: ignore[arg-type]
            "https://example.test/webhook",
            payload,
        )

    assert result["status_code"] == 201
    messages = [record.getMessage() for record in caplog.records]
    started = [message for message in messages if "GHL inbound webhook request started" in message]
    success = [message for message in messages if "GHL inbound webhook success" in message]
    assert started
    assert success
    assert '"phase": "webhook request started"' in started[0]
    assert '"method": "POST"' in started[0]
    assert '"event": "abandoned.cart"' in started[0]
    assert '"contactId_masked": "ghl-***99"' in started[0]
    assert '"status_code": 201' in success[0]
    assert '"success": true' in success[0]
    assert "buyer@example.com" not in "".join(messages)
    assert "0500000000" not in "".join(messages)
    assert "https://store.test/checkout/cart-1" not in "".join(messages)
    assert "Authorization" not in "".join(messages)


async def test_inbound_webhook_http_error_is_logged_as_failure(caplog) -> None:
    caplog.set_level(logging.ERROR)

    class FakeResponse:
        status_code = 500
        text = "upstream error"

        def json(self) -> dict[str, object]:
            return {"error": "upstream error"}

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, headers: dict[str, str] | None = None, json: dict[str, object] | None = None):
            return FakeResponse()

    with patch("salla_ghl.integrations.ghl.client.httpx.AsyncClient", FakeAsyncClient):
        try:
            await GHLClient(None).post_inbound_webhook(  # type: ignore[arg-type]
                "https://example.test/webhook",
                {"event": "abandoned.cart", "contactId": "ghl-contact-99"},
            )
        except GHLClientError as exc:
            assert exc.status_code == 500
        else:
            raise AssertionError("HTTP 500 must fail the inbound webhook")

    failed = [record.getMessage() for record in caplog.records if "GHL inbound webhook failed" in record.getMessage()]
    assert failed
    assert '"phase": "failure"' in failed[0]
    assert '"success": false' in failed[0]
    assert '"status_code": 500' in failed[0]
    assert '"event": "abandoned.cart"' in failed[0]
