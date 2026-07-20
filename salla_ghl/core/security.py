import hashlib
import hmac

from fastapi import HTTPException

from salla_ghl.core.config import settings


def payload_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def verify_salla_signature(raw_body: bytes, signature: str | None) -> None:
    if not settings.salla_webhook_secret:
        return
    if not signature:
        raise HTTPException(status_code=401, detail="Missing Salla signature")

    computed = hmac.new(
        settings.salla_webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, computed):
        raise HTTPException(status_code=401, detail="Invalid Salla signature")


def verify_salla_token(authorization: str | None) -> None:
    if not settings.salla_webhook_token:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Salla authorization token")

    expected_values = {settings.salla_webhook_token, f"Bearer {settings.salla_webhook_token}"}
    if authorization not in expected_values:
        raise HTTPException(status_code=401, detail="Invalid Salla authorization token")


def verify_admin_api_key(api_key: str | None) -> None:
    if not settings.admin_api_key:
        return
    if not api_key or not hmac.compare_digest(api_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid admin API key")
