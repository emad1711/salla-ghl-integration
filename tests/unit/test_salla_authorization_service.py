from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from salla_ghl.db.models import Base
from salla_ghl.services.salla_authorization_service import SallaAuthorizationService


async def test_receive_authorization_persists_tokens_without_public_exposure() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    payload = {
        "event": "app.store.authorize",
        "merchant": {"id": 123456, "name": "Melen"},
        "data": {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
        },
    }

    async with session_factory() as session:
        service = SallaAuthorizationService(session)
        integration = await service.receive_authorization(payload)
        status = service.public_status(integration)
        stores = [service.public_store(store) for store in await service.integrations.list_all()]

    assert integration.store_id == "123456"
    assert integration.store_name == "Melen"
    assert integration.access_token == "access-token"
    assert integration.refresh_token == "refresh-token"
    assert integration.expires_at is not None
    assert status["token_exists"] is True
    assert "access_token" not in status
    assert stores[0]["refresh_token_exists"] is True
    assert "refresh_token" not in stores[0]
