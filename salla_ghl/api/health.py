from fastapi import APIRouter

from salla_ghl.core.config import settings
from salla_ghl.db.session import check_database
from salla_ghl.workers.queue import check_queue

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "service": settings.service_name,
        "environment": settings.app_env,
        "allowed_events": sorted(settings.salla_allowed_events),
        "ghl_configured": settings.ghl_configured,
        "ghl_abandoned_checkout_webhook_configured": bool(settings.ghl_abandoned_checkout_webhook_url),
        "app_base_url_configured": bool(settings.app_base_url),
        "salla_signature_configured": settings.salla_signature_configured,
        "database": await check_database(),
        "queue": await check_queue(),
    }
