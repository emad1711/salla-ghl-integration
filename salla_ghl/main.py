from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from salla_ghl.api import admin, health, internal, webhooks
from salla_ghl.core.logging import configure_logging
from salla_ghl.core.monitoring import configure_monitoring
from salla_ghl.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    configure_monitoring()
    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Salla to GoHighLevel Production Integration", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(webhooks.router)
    app.include_router(admin.router)
    app.include_router(internal.router)
    return app


app = create_app()
