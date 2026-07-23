from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
import logging

from fastapi import FastAPI, Request

from salla_ghl.api import admin, health, internal, webhooks
from salla_ghl.core.logging import configure_logging
from salla_ghl.core.monitoring import configure_monitoring
from salla_ghl.db.session import init_db

logger = logging.getLogger(__name__)


def raw_headers(request: Request) -> list[tuple[str, str]]:
    return [
        (name.decode("latin-1", errors="replace"), value.decode("latin-1", errors="replace"))
        for name, value in request.scope.get("headers", [])
    ]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    configure_monitoring()
    await init_db()
    for route in app.routes:
        if hasattr(route, "path"):
            print(route.path, getattr(route, "methods", None))
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Salla to GoHighLevel Production Integration", lifespan=lifespan)

    @app.api_route("/debug/test", methods=["GET", "POST"])
    async def debug_test(request: Request) -> dict[str, object]:
        raw_body = await request.body()
        logger.warning(
            "Debug test route %s",
            json.dumps(
                {
                    "method": request.method,
                    "url": str(request.url),
                    "headers": dict(request.headers),
                    "raw_headers": raw_headers(request),
                    "x_salla_security_strategy": request.headers.get("x-salla-security-strategy"),
                    "x_salla_signature": request.headers.get("x-salla-signature"),
                    "authorization": request.headers.get("authorization"),
                    "raw_body": raw_body.decode("utf-8", errors="replace"),
                },
                ensure_ascii=False,
            ),
        )
        return {"ok": True, "message": "debug route works"}

    @app.middleware("http")
    async def log_every_request(request: Request, call_next):
        response = await call_next(request)
        logger.warning(
            "Incoming request debug %s",
            json.dumps(
                {
                    "method": request.method,
                    "url": str(request.url),
                    "headers": dict(request.headers),
                    "raw_headers": raw_headers(request),
                    "x_salla_security_strategy": request.headers.get("x-salla-security-strategy"),
                    "x_salla_signature": request.headers.get("x-salla-signature"),
                    "authorization": request.headers.get("authorization"),
                    "status_code": response.status_code,
                },
                ensure_ascii=False,
            ),
        )
        return response

    app.include_router(health.router)
    app.include_router(webhooks.router)
    app.include_router(admin.router)
    app.include_router(internal.router)
    return app


app = create_app()
