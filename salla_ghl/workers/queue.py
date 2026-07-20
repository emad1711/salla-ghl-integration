import json

import redis.asyncio as redis

from salla_ghl.core.config import settings

QUEUE_NAME = "salla_ghl_events"


async def get_redis() -> redis.Redis | None:
    if not settings.enable_redis:
        return None
    return redis.from_url(settings.redis_url, decode_responses=True)


async def enqueue_event(event_id: str) -> bool:
    client = await get_redis()
    if not client:
        return False
    await client.lpush(QUEUE_NAME, json.dumps({"event_id": event_id}))
    await client.aclose()
    return True


async def pop_event(timeout_seconds: int = 5) -> str | None:
    client = await get_redis()
    if not client:
        return None
    result = await client.brpop(QUEUE_NAME, timeout=timeout_seconds)
    await client.aclose()
    if not result:
        return None
    _, payload = result
    return json.loads(payload).get("event_id")


async def check_queue() -> dict[str, object]:
    if not settings.enable_redis:
        return {"ok": True, "mode": "local"}
    try:
        client = await get_redis()
        if not client:
            return {"ok": False, "error": "Redis disabled"}
        await client.ping()
        await client.aclose()
        return {"ok": True, "mode": "redis"}
    except Exception as exc:
        return {"ok": False, "mode": "redis", "error": str(exc)}
