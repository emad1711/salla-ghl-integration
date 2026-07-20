from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


def get_nested(source: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = source
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, "", []):
            return current
    return None


def as_amount(value: Any) -> Decimal:
    if isinstance(value, dict):
        value = value.get("amount")
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def split_name(name: str | None) -> tuple[str | None, str | None]:
    if not name:
        return None, None
    parts = name.strip().split()
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def normalize_tag(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in str(value).strip())
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or None


@dataclass(frozen=True)
class NormalizedCustomer:
    salla_customer_id: str | None
    first_name: str | None
    last_name: str | None
    name: str | None
    email: str | None
    phone: str | None
    city: str | None = None
    address1: str | None = None
    postal_code: str | None = None
    country: str | None = None


@dataclass(frozen=True)
class NormalizedOrderItem:
    product_id: str | None
    sku: str | None
    name: str | None
    quantity: int
    unit_price: Decimal
    total_price: Decimal


@dataclass(frozen=True)
class NormalizedOrder:
    salla_order_id: str
    reference_id: str | None
    status: str | None
    payment_status: str | None
    fulfillment_status: str | None
    total_amount: Decimal
    currency: str
    admin_url: str | None
    items: list[NormalizedOrderItem] = field(default_factory=list)


@dataclass(frozen=True)
class NormalizedCart:
    salla_cart_id: str | None
    checkout_url: str | None
    total_amount: Decimal
    currency: str
    items: list[NormalizedOrderItem] = field(default_factory=list)


@dataclass(frozen=True)
class NormalizedProductStock:
    product_id: str | None
    sku: str | None
    name: str | None
    quantity: int | None
    in_stock: bool | None


@dataclass(frozen=True)
class NormalizedEvent:
    event_type: str
    merchant_id: str | None
    event_id: str | None
    customer: NormalizedCustomer | None
    order: NormalizedOrder | None
    cart: NormalizedCart | None
    product_stock: NormalizedProductStock | None
    raw_payload: dict[str, Any]


class SallaNormalizer:
    def normalize(self, payload: dict[str, Any]) -> NormalizedEvent:
        event_type = str(payload.get("event") or "")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        customer = self._normalize_customer(data, event_type)
        order = self._normalize_order(data, event_type) if self._is_order_event(event_type) else None
        cart = self._normalize_cart(data) if self._is_cart_event(event_type) else None
        product_stock = self._normalize_product_stock(data) if self._is_product_stock_event(event_type) else None
        return NormalizedEvent(
            event_type=event_type,
            merchant_id=str(payload.get("merchant")) if payload.get("merchant") else None,
            event_id=str(payload.get("id") or payload.get("event_id") or ""),
            customer=customer,
            order=order,
            cart=cart,
            product_stock=product_stock,
            raw_payload=payload,
        )

    def _is_order_event(self, event_type: str) -> bool:
        return event_type.startswith("order.")

    def _is_cart_event(self, event_type: str) -> bool:
        normalized = event_type.replace("_", ".")
        return normalized.startswith("cart.") or normalized.startswith("abandoned.cart")

    def _is_product_stock_event(self, event_type: str) -> bool:
        normalized = event_type.replace("_", ".")
        return normalized.startswith("product.") and (
            any(part in normalized for part in ("stock", "quantity")) or normalized == "product.updated"
        )

    def _normalize_customer(self, data: dict[str, Any], event_type: str) -> NormalizedCustomer | None:
        customer = get_nested(data, "customer") or (data if event_type.startswith("customer.") else {})
        shipping_receiver = get_nested(data, "shipping.receiver") or {}
        shipping_address = get_nested(data, "shipping.address", "shipping.ship_to", "ship_to") or {}

        name = (
            get_nested(customer, "name", "full_name")
            or get_nested(shipping_receiver, "name")
            or get_nested(data, "customer_name")
        )
        first_name = get_nested(customer, "first_name", "firstname")
        last_name = get_nested(customer, "last_name", "lastname")
        if not first_name and not last_name:
            first_name, last_name = split_name(name)

        email = (
            get_nested(customer, "email")
            or get_nested(shipping_receiver, "email")
            or get_nested(data, "customer_email")
        )
        phone = (
            get_nested(customer, "mobile", "phone")
            or get_nested(shipping_receiver, "phone", "mobile")
            or get_nested(data, "customer_mobile", "customer_phone")
        )
        salla_customer_id = get_nested(customer, "id")

        if not any([salla_customer_id, email, phone, name]):
            return None

        return NormalizedCustomer(
            salla_customer_id=str(salla_customer_id) if salla_customer_id else None,
            first_name=first_name,
            last_name=last_name,
            name=name,
            email=email,
            phone=phone,
            city=get_nested(shipping_address, "city"),
            address1=get_nested(shipping_address, "shipping_address", "address_line", "address"),
            postal_code=get_nested(shipping_address, "postal_code", "postalCode"),
            country=get_nested(shipping_address, "country_code", "country"),
        )

    def _normalize_order(self, data: dict[str, Any], event_type: str) -> NormalizedOrder | None:
        order_id = get_nested(data, "id", "reference_id")
        if not order_id:
            return None
        total = as_amount(get_nested(data, "amounts.total", "total", "total.amount"))
        currency = (
            get_nested(data, "amounts.total.currency", "total.currency")
            or get_nested(data, "currency")
            or "SAR"
        )
        status = get_nested(data, "status.name", "status.slug", "status")
        if not status:
            status = self._status_from_order_event(event_type)

        return NormalizedOrder(
            salla_order_id=str(order_id),
            reference_id=str(get_nested(data, "reference_id") or "") or None,
            status=status,
            payment_status=get_nested(data, "payment_status", "payment.status", "payment_method"),
            fulfillment_status=get_nested(data, "shipment.status", "shipping.status", "fulfillment_status"),
            total_amount=total,
            currency=str(currency),
            admin_url=get_nested(data, "urls.admin", "url.admin"),
            items=self._normalize_items(data),
        )

    def _status_from_order_event(self, event_type: str) -> str | None:
        event_statuses = {
            "order.created": "created",
            "order.completed": "completed",
            "order.delivered": "delivered",
            "order.cancelled": "cancelled",
            "order.canceled": "cancelled",
            "order.refunded": "refunded",
        }
        if event_type in event_statuses:
            return event_statuses[event_type]
        if (
            event_type.endswith(".status.updated")
            or event_type.endswith(".status_changed")
            or event_type.endswith(".updated_status")
        ):
            return "updated"
        return None

    def _normalize_items(self, data: dict[str, Any]) -> list[NormalizedOrderItem]:
        raw_items = get_nested(data, "items") or get_nested(data, "products") or []
        if not isinstance(raw_items, list):
            return []
        items = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            quantity = int(get_nested(item, "quantity") or 1)
            unit_price = as_amount(get_nested(item, "price", "product.price"))
            total_price = unit_price * quantity
            items.append(
                NormalizedOrderItem(
                    product_id=str(get_nested(item, "id", "product.id") or "") or None,
                    sku=get_nested(item, "sku", "product.sku"),
                    name=get_nested(item, "name", "product.name"),
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total_price,
                )
            )
        return items

    def _normalize_cart(self, data: dict[str, Any]) -> NormalizedCart | None:
        cart_id = get_nested(data, "id", "cart.id", "checkout.id")
        total = as_amount(get_nested(data, "amounts.total", "total", "total.amount", "cart.total"))
        currency = (
            get_nested(data, "amounts.total.currency", "total.currency", "cart.currency")
            or get_nested(data, "currency")
            or "SAR"
        )
        checkout_url = get_nested(data, "checkout_url", "urls.checkout", "url", "cart.url")
        if not any([cart_id, checkout_url, data.get("items"), data.get("products")]):
            return None
        return NormalizedCart(
            salla_cart_id=str(cart_id) if cart_id else None,
            checkout_url=checkout_url,
            total_amount=total,
            currency=str(currency),
            items=self._normalize_items(data),
        )

    def _normalize_product_stock(self, data: dict[str, Any]) -> NormalizedProductStock | None:
        product = get_nested(data, "product") or data
        quantity = get_nested(product, "quantity", "stock_quantity", "stock", "metadata.quantity")
        try:
            normalized_quantity = int(quantity) if quantity not in (None, "") else None
        except (TypeError, ValueError):
            normalized_quantity = None
        in_stock = self._as_bool(get_nested(product, "in_stock", "is_available", "available"))
        if in_stock is None and normalized_quantity is not None:
            in_stock = normalized_quantity > 0
        if not any([get_nested(product, "id"), get_nested(product, "sku"), get_nested(product, "name"), quantity]):
            return None
        return NormalizedProductStock(
            product_id=str(get_nested(product, "id") or "") or None,
            sku=get_nested(product, "sku"),
            name=get_nested(product, "name"),
            quantity=normalized_quantity,
            in_stock=in_stock,
        )

    def _as_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return value > 0
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "available", "in_stock"}:
            return True
        if normalized in {"0", "false", "no", "off", "unavailable", "out_of_stock"}:
            return False
        return None
