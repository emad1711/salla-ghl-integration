from typing import Any, TypedDict


class GHLContactPayload(TypedDict, total=False):
    locationId: str
    source: str
    firstName: str
    lastName: str
    email: str
    phone: str
    tags: list[str]
    customFields: list[dict[str, Any]]
