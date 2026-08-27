from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from salla_ghl.core.config import settings
from salla_ghl.db.models import Base, Customer, Order
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

    assert payload["event"] == "salla.cart_abandoned"
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
    finally:
        object.__setattr__(settings, "ghl_location_id", old_location_id)
        object.__setattr__(settings, "ghl_abandoned_checkout_webhook_url", old_webhook_url)
