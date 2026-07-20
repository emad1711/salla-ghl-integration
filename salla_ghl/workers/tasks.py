import asyncio
import logging

from salla_ghl.core.logging import configure_logging
from salla_ghl.db.session import SessionLocal, init_db
from salla_ghl.services.event_service import EventService
from salla_ghl.workers.queue import pop_event

logger = logging.getLogger(__name__)


async def process_event(event_id: str) -> dict[str, object]:
    async with SessionLocal() as session:
        return await EventService(session).process_event(event_id)


async def worker_loop() -> None:
    configure_logging()
    await init_db()
    logger.info("Worker started")
    while True:
        event_id = await pop_event()
        if not event_id:
            await asyncio.sleep(1)
            continue
        try:
            await process_event(event_id)
        except Exception:
            logger.exception("Worker failed to process event", extra={"event_id": event_id})


def main() -> None:
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
