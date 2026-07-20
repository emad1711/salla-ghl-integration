import logging

from salla_ghl.core.config import settings

logger = logging.getLogger(__name__)


def configure_monitoring() -> None:
    if not settings.enable_sentry or not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        logger.warning("Sentry is enabled but sentry-sdk is not installed")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.1,
    )
