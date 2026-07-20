from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.core.security import verify_admin_api_key
from salla_ghl.db.session import get_session
from salla_ghl.repositories.salla_integrations import SallaIntegrationRepository
from salla_ghl.services.salla_authorization_service import SallaAuthorizationService

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/salla/status")
async def salla_status(
    session: AsyncSession = Depends(get_session),
    x_admin_api_key: str | None = Header(default=None),
) -> dict[str, object]:
    verify_admin_api_key(x_admin_api_key)
    integration = await SallaIntegrationRepository(session).latest()
    return SallaAuthorizationService(session).public_status(integration)


@router.get("/salla/stores")
async def salla_stores(
    session: AsyncSession = Depends(get_session),
    x_admin_api_key: str | None = Header(default=None),
) -> dict[str, object]:
    verify_admin_api_key(x_admin_api_key)
    integrations = await SallaIntegrationRepository(session).list_all()
    service = SallaAuthorizationService(session)
    return {"stores": [service.public_store(integration) for integration in integrations]}
