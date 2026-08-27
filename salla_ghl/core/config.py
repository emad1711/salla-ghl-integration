import os
from dataclasses import dataclass


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value or default)
    except ValueError:
        return default


def _float(value: str | None, default: float) -> float:
    try:
        return float(value or default)
    except ValueError:
        return default


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


def _database_url(value: str | None) -> str:
    url = value or "sqlite+aiosqlite:///./salla_ghl.db"
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    service_name: str = os.getenv("SERVICE_NAME", "salla-ghl-webhook")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    app_base_url: str = os.getenv("APP_BASE_URL", "").rstrip("/")

    database_url: str = _database_url(os.getenv("DATABASE_URL"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    enable_redis: bool = _bool(os.getenv("ENABLE_REDIS"), False)

    salla_webhook_secret: str = os.getenv("SALLA_WEBHOOK_SECRET", "")
    salla_webhook_token: str = os.getenv("SALLA_WEBHOOK_TOKEN", "")
    salla_client_id: str = os.getenv("SALLA_CLIENT_ID", "")
    salla_client_secret: str = os.getenv("SALLA_CLIENT_SECRET", "")
    salla_api_base_url: str = os.getenv("SALLA_API_BASE_URL", "https://api.salla.dev/admin/v2").rstrip("/")
    # Legacy fallback only. Production installs should persist app.store.authorize tokens.
    salla_api_token: str = os.getenv("SALLA_API_TOKEN", "")
    salla_allowed_events: tuple[str, ...] = tuple(
        event.strip()
        for event in os.getenv(
            "SALLA_ALLOWED_EVENTS",
            "order.created,order.updated,order.status.updated,order.completed,order.delivered,order.cancelled,order.refunded,"
            "order.canceled,order.status_changed,order.updated_status,customer.created,customer.registered,"
            "customer.updated,customer.created_or_registered,cart.abandoned,abandoned_cart.created,"
            "abandoned.cart.created,product.stock.updated,product.quantity.updated,product.updated",
        ).split(",")
        if event.strip()
    )

    ghl_base_url: str = os.getenv("GHL_BASE_URL", "https://services.leadconnectorhq.com").rstrip("/")
    ghl_api_version: str = os.getenv("GHL_API_VERSION", "2021-07-28")
    ghl_private_integration_token: str = os.getenv("GHL_PRIVATE_INTEGRATION_TOKEN", "")
    ghl_location_id: str = os.getenv("GHL_LOCATION_ID", "")
    ghl_source: str = os.getenv("GHL_SOURCE", "Salla")
    ghl_timeout_seconds: float = _float(os.getenv("GHL_TIMEOUT_SECONDS"), 20)
    ghl_pipeline_id: str = os.getenv("GHL_PIPELINE_ID", "")
    ghl_pipeline_stage_id: str = os.getenv("GHL_PIPELINE_STAGE_ID", "")
    ghl_opportunity_status: str = os.getenv("GHL_OPPORTUNITY_STATUS", "open")
    ghl_abandoned_checkout_webhook_url: str = os.getenv("GHL_ABANDONED_CHECKOUT_WEBHOOK_URL", "")

    vip_total_spent_threshold: float = _float(
        os.getenv("VIP_TOTAL_SPENT_THRESHOLD") or os.getenv("GHL_VIP_ORDER_TOTAL_THRESHOLD"),
        1000,
    )
    loyalty_points_per_currency_unit: float = _float(os.getenv("LOYALTY_POINTS_PER_CURRENCY_UNIT"), 1)
    loyalty_points_per_order: int = _int(os.getenv("LOYALTY_POINTS_PER_ORDER"), 0)
    loyalty_eligible_statuses: tuple[str, ...] = _csv(
        os.getenv("LOYALTY_ELIGIBLE_STATUSES", "created,paid,completed,delivered")
    )
    inactive_days_threshold: int = _int(os.getenv("INACTIVE_DAYS_THRESHOLD"), 60)
    review_request_delay_hours: int = _int(os.getenv("REVIEW_REQUEST_DELAY_HOURS"), 48)
    abandoned_cart_delays_minutes: tuple[int, ...] = tuple(
        _int(value.strip(), 0)
        for value in os.getenv("ABANDONED_CART_DELAYS_MINUTES", "30,1440,2880").split(",")
        if value.strip()
    )

    max_retry_attempts: int = _int(os.getenv("MAX_RETRY_ATTEMPTS"), 5)
    retry_base_delay_seconds: int = _int(os.getenv("RETRY_BASE_DELAY_SECONDS"), 30)

    sentry_dsn: str = os.getenv("SENTRY_DSN", "")
    enable_sentry: bool = _bool(os.getenv("ENABLE_SENTRY"), False)

    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")

    @property
    def ghl_configured(self) -> bool:
        return bool(self.ghl_private_integration_token and self.ghl_location_id)

    @property
    def salla_signature_configured(self) -> bool:
        return bool(self.salla_webhook_secret)

    @property
    def salla_orders_webhook_url(self) -> str:
        if not self.app_base_url:
            return ""
        return f"{self.app_base_url}/webhooks/salla/orders"

    @property
    def salla_authorize_webhook_url(self) -> str:
        if not self.app_base_url:
            return ""
        return f"{self.app_base_url}/webhooks/salla/authorize"


settings = Settings()
