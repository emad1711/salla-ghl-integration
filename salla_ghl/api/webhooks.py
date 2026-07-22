import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.core.security import verify_salla_signature, verify_salla_token
from salla_ghl.db.session import get_session
from salla_ghl.services.event_service import EventService
from salla_ghl.services.salla_authorization_service import SallaAuthorizationError, SallaAuthorizationService
from salla_ghl.workers.queue import enqueue_event

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])


@router.get("/debug/test")
async def debug_test() -> dict[str, object]:
    return {"ok": True, "message": "debug route works"}


async def process_in_background(event_id: str) -> None:
    async for session in get_session():
        await EventService(session).process_event(event_id)


@router.post("/webhooks/salla", status_code=202)
async def salla_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    x_salla_signature: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    raw_body = await request.body()
    verify_salla_signature(raw_body, x_salla_signature)
    verify_salla_token(authorization)

    try:
        event_id, created, status = await EventService(session).receive(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created:
        queued = await enqueue_event(event_id)
        if not queued:
            background_tasks.add_task(process_in_background, event_id)
    return {"ok": True, "event_id": event_id, "status": status}


@router.post("/webhooks/salla/orders")
async def salla_orders_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    x_salla_signature: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    raw_body = await request.body()
    logger.warning(
        "Salla orders webhook debug %s",
        json.dumps(
            {
                "request_url": str(request.url),
                "headers": dict(request.headers),
                "x_salla_signature": x_salla_signature,
                "authorization": authorization,
                "raw_body": raw_body.decode("utf-8", errors="replace"),
            },
            ensure_ascii=False,
        ),
    )
    # Backwards-compatible URL already configured in Salla.
    response = await salla_webhook(
        request=request,
        background_tasks=background_tasks,
        session=session,
        x_salla_signature=x_salla_signature,
        authorization=authorization,
    )
    return response


@router.post("/webhooks/salla/authorize", status_code=202)
async def salla_authorize_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_salla_signature: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    raw_body = await request.body()
    verify_salla_signature(raw_body, x_salla_signature)
    verify_salla_token(authorization)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    try:
        integration = await SallaAuthorizationService(session).receive_authorization(payload)
    except SallaAuthorizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "ok": True,
        "event": SallaAuthorizationService.AUTHORIZE_EVENT,
        "store_id": integration.store_id,
        "store_name": integration.store_name,
        "token_saved": True,
        "expires_at": integration.expires_at,
    }
