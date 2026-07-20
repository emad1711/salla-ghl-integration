from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.core.security import verify_admin_api_key
from salla_ghl.db.session import get_session
from salla_ghl.repositories.events import EventRepository
from salla_ghl.services.event_service import EventService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/events/{event_id}")
async def get_event(
    event_id: str,
    session: AsyncSession = Depends(get_session),
    x_admin_api_key: str | None = Header(default=None),
) -> dict[str, object]:
    verify_admin_api_key(x_admin_api_key)
    event = await EventRepository(session).get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return {
        "id": event.id,
        "event_type": event.event_type,
        "status": event.status,
        "error_message": event.error_message,
        "retry_count": event.retry_count,
        "received_at": event.received_at,
        "processed_at": event.processed_at,
    }


@router.post("/events/{event_id}/retry")
async def retry_event(
    event_id: str,
    session: AsyncSession = Depends(get_session),
    x_admin_api_key: str | None = Header(default=None),
) -> dict[str, object]:
    verify_admin_api_key(x_admin_api_key)
    return await EventService(session).process_event(event_id)


@router.post("/sync/customers")
async def sync_customers(x_admin_api_key: str | None = Header(default=None)) -> dict[str, object]:
    verify_admin_api_key(x_admin_api_key)
    return {"ok": True, "status": "not_configured", "message": "Salla customer backfill requires Merchant API credentials."}


@router.post("/sync/orders")
async def sync_orders(x_admin_api_key: str | None = Header(default=None)) -> dict[str, object]:
    verify_admin_api_key(x_admin_api_key)
    return {"ok": True, "status": "not_configured", "message": "Salla order backfill requires Merchant API credentials."}
