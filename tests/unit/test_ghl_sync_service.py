from decimal import Decimal

from salla_ghl.core.config import settings
from salla_ghl.db.models import Customer, Order
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
