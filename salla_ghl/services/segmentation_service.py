from decimal import Decimal

from salla_ghl.core.config import settings
from salla_ghl.db.models import Customer, Order
from salla_ghl.integrations.salla.normalizer import normalize_tag


class SegmentationService:
    def tags_for_customer(self, customer: Customer, order: Order | None, product_skus: list[str]) -> set[str]:
        tags = {"salla"}

        if customer.purchase_count <= 1:
            tags.add("salla-new-customer")
        else:
            tags.add("salla-returning-customer")

        if Decimal(customer.total_spent or 0) >= Decimal(str(settings.vip_total_spent_threshold)):
            tags.add("salla-vip-customer")

        if customer.status == "inactive":
            tags.add("salla-inactive-customer")

        if order:
            tags.add("salla-order")
            status_tag = normalize_tag(order.status)
            if status_tag:
                tags.add(f"salla-status-{status_tag}")
            if status_tag in {"paid", "completed"}:
                tags.add("salla-order-paid")
                tags.add("salla-post-purchase")
            if status_tag in {"delivered", "completed"}:
                tags.add("salla-order-delivered")

        for sku in product_skus:
            product_tag = normalize_tag(sku)
            if product_tag:
                tags.add(f"salla-product-{product_tag}"[:50])

        return tags
