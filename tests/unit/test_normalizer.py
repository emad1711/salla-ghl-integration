from decimal import Decimal

from salla_ghl.integrations.salla.normalizer import SallaNormalizer


def test_normalizes_order_payload() -> None:
    payload = {
        "event": "order.created",
        "merchant": 123,
        "data": {
            "id": 456,
            "customer": {"name": "Test User", "email": "test@example.com", "mobile": "+966500000000"},
            "amounts": {"total": {"amount": 1500, "currency": "SAR"}},
            "status": {"name": "paid"},
            "items": [{"sku": "SKU-1", "name": "Product", "quantity": 2, "price": {"amount": 10}}],
        },
    }

    normalized = SallaNormalizer().normalize(payload)

    assert normalized.event_type == "order.created"
    assert normalized.customer is not None
    assert normalized.customer.email == "test@example.com"
    assert normalized.order is not None
    assert normalized.order.salla_order_id == "456"
    assert normalized.order.total_amount == 1500
    assert normalized.order.items[0].sku == "SKU-1"


def test_completed_event_sets_status_when_missing() -> None:
    payload = {
        "event": "order.completed",
        "data": {"id": 1, "customer": {"email": "test@example.com"}},
    }

    normalized = SallaNormalizer().normalize(payload)

    assert normalized.order is not None
    assert normalized.order.status == "completed"


def test_created_event_sets_status_when_missing() -> None:
    payload = {
        "event": "order.created",
        "data": {"id": 1, "customer": {"email": "test@example.com"}},
    }

    normalized = SallaNormalizer().normalize(payload)

    assert normalized.order is not None
    assert normalized.order.status == "created"


def test_status_updated_event_normalizes_status_from_payload() -> None:
    payload = {
        "event": "order.status.updated",
        "data": {
            "id": 1,
            "customer": {"email": "test@example.com"},
            "status": {"slug": "shipped"},
        },
    }

    normalized = SallaNormalizer().normalize(payload)

    assert normalized.order is not None
    assert normalized.order.status == "shipped"


def test_normalizes_documented_abandoned_cart_event() -> None:
    payload = {
        "event": "abandoned.cart",
        "merchant": 123,
        "data": {
            "id": "cart-1",
            "checkout_url": "https://store.test/checkout/cart-1",
            "total": {"amount": 200, "currency": "SAR"},
            "items": [{"sku": "SKU-2", "name": "Cart Product", "quantity": 1, "price": {"amount": 200}}],
            "customer": {"id": "55", "name": "Buyer Test", "email": "buyer@example.com", "mobile": "0500000000"},
        },
    }

    normalized = SallaNormalizer().normalize(payload)

    assert normalized.event_type == "abandoned.cart"
    assert normalized.customer is not None
    assert normalized.customer.salla_customer_id == "55"
    assert normalized.customer.email == "buyer@example.com"
    assert normalized.customer.phone == "0500000000"
    assert normalized.cart is not None
    assert normalized.cart.salla_cart_id == "cart-1"
    assert normalized.cart.checkout_url == "https://store.test/checkout/cart-1"
    assert normalized.cart.total_amount == 200
    assert normalized.cart.currency == "SAR"
    assert normalized.cart.items[0].sku == "SKU-2"


def test_normalizes_abandoned_cart_payload() -> None:
    payload = {
        "event": "cart.abandoned",
        "data": {
            "id": "cart-1",
            "customer_email": "buyer@example.com",
            "checkout_url": "https://store.test/checkout/cart-1",
            "total": {"amount": 200, "currency": "SAR"},
            "items": [{"sku": "SKU-2", "name": "Cart Product", "quantity": 1, "price": {"amount": 200}}],
        },
    }

    normalized = SallaNormalizer().normalize(payload)

    assert normalized.customer is not None
    assert normalized.customer.email == "buyer@example.com"
    assert normalized.cart is not None
    assert normalized.cart.salla_cart_id == "cart-1"
    assert normalized.cart.checkout_url == "https://store.test/checkout/cart-1"
    assert normalized.cart.items[0].sku == "SKU-2"


def test_customer_registered_payload_uses_customer_data_as_identity() -> None:
    payload = {
        "event": "customer.registered",
        "data": {"id": 55, "name": "New Customer", "email": "new@example.com", "mobile": "+966511111111"},
    }

    normalized = SallaNormalizer().normalize(payload)

    assert normalized.customer is not None
    assert normalized.customer.salla_customer_id == "55"
    assert normalized.customer.email == "new@example.com"
    assert normalized.customer.first_name == "New"
    assert normalized.customer.last_name == "Customer"


def test_normalizes_official_abandoned_cart_purchased_event() -> None:
    payload = {
        "event": "abandoned.cart.purchased",
        "merchant": 935918575,
        "data": {
            "id": 1305879817,
            "status": "purchased",
            "currency": "SAR",
            "total": 34.99,
            "subtotal": 30.43,
            "total_discount": 0,
        },
    }

    normalized = SallaNormalizer().normalize(payload)

    assert normalized.event_type == "abandoned.cart.purchased"
    assert normalized.customer is None
    assert normalized.order is None
    assert normalized.cart is not None
    assert normalized.cart.salla_cart_id == "1305879817"
    assert normalized.cart.checkout_url is None
    assert normalized.cart.total_amount == Decimal("34.99")
    assert normalized.cart.currency == "SAR"


def test_extracts_official_checkout_url_from_purchased_payload_when_present() -> None:
    payload = {
        "event": "abandoned.cart.purchased",
        "data": {
            "id": "cart-1",
            "status": "purchased",
            "checkout_url": "https://store.test/checkout/cart-1",
            "total": {"amount": 80.5, "currency": "SAR"},
            "customer": {"id": "55", "name": "Buyer Test", "email": "buyer@example.com", "mobile": "0500000000"},
            "items": [{"sku": "SKU-2", "name": "Cart Product", "quantity": 1, "price": {"amount": 80.5}}],
        },
    }

    normalized = SallaNormalizer().normalize(payload)

    assert normalized.event_type == "abandoned.cart.purchased"
    assert normalized.customer is not None
    assert normalized.customer.email == "buyer@example.com"
    assert normalized.cart is not None
    assert normalized.cart.checkout_url == "https://store.test/checkout/cart-1"
    assert normalized.cart.salla_cart_id == "cart-1"
    assert normalized.cart.total_amount == 80.5


def test_missing_checkout_url_is_not_invented() -> None:
    payload = {
        "event": "abandoned.cart.purchased",
        "data": {
            "id": "cart-1",
            "status": "purchased",
            "currency": "SAR",
            "total": 34.99,
            "customer": {"id": "55", "email": "buyer@example.com", "mobile": "0500000000"},
        },
    }

    normalized = SallaNormalizer().normalize(payload)

    assert normalized.cart is not None
    assert normalized.cart.checkout_url is None
    assert "salla.sa" not in str(normalized.raw_payload)


def test_product_stock_payload_does_not_create_customer_from_product_id() -> None:
    payload = {
        "event": "product.updated",
        "data": {"id": 99, "sku": "SKU-3", "name": "Restocked Product", "quantity": 8, "in_stock": "true"},
    }

    normalized = SallaNormalizer().normalize(payload)

    assert normalized.customer is None
    assert normalized.product_stock is not None
    assert normalized.product_stock.product_id == "99"
    assert normalized.product_stock.sku == "SKU-3"
    assert normalized.product_stock.quantity == 8
    assert normalized.product_stock.in_stock is True
