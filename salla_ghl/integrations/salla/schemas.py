from typing import Any, TypedDict


class SallaWebhookPayload(TypedDict, total=False):
    event: str
    merchant: int | str
    created_at: str
    data: dict[str, Any]
