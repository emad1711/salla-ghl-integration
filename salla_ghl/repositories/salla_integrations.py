from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from salla_ghl.db.models import SallaIntegration, now_utc


class SallaIntegrationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_store_id(self, store_id: str) -> SallaIntegration | None:
        result = await self.session.execute(select(SallaIntegration).where(SallaIntegration.store_id == store_id))
        return result.scalar_one_or_none()

    async def latest(self) -> SallaIntegration | None:
        result = await self.session.execute(
            select(SallaIntegration).order_by(SallaIntegration.updated_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[SallaIntegration]:
        result = await self.session.execute(select(SallaIntegration).order_by(SallaIntegration.updated_at.desc()))
        return list(result.scalars().all())

    async def upsert(
        self,
        *,
        store_id: str,
        store_name: str | None,
        access_token: str,
        refresh_token: str | None,
        expires_at: datetime | None,
    ) -> SallaIntegration:
        integration = await self.get_by_store_id(store_id)
        if not integration:
            integration = SallaIntegration(
                store_id=store_id,
                store_name=store_name,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
            )
            self.session.add(integration)
        else:
            integration.store_name = store_name or integration.store_name
            integration.access_token = access_token
            integration.refresh_token = refresh_token or integration.refresh_token
            integration.expires_at = expires_at
            integration.updated_at = now_utc()
        await self.session.flush()
        return integration
