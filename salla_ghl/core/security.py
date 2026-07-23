import hashlib
import hmac
import json
import logging

from fastapi import HTTPException

from salla_ghl.core.config import settings

logger = logging.getLogger(__name__)


def payload_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def _log_webhook_401(
    *,
    reason: str,
    request_path: str | None,
    x_salla_signature: str | None,
    authorization: str | None,
    signature_validation_passed: bool,
    authorization_validation_passed: bool,
    line: str,
) -> None:
    logger.warning(
        "Salla webhook 401 debug %s",
        json.dumps(
            {
                "reason": reason,
                "request_path": request_path,
                "x_salla_signature": x_salla_signature,
                "authorization": authorization,
                "salla_webhook_secret_loaded": bool(settings.salla_webhook_secret),
                "signature_validation_passed": signature_validation_passed,
                "authorization_validation_passed": authorization_validation_passed,
                "line": line,
            },
            ensure_ascii=False,
        ),
    )


def verify_salla_signature(
    raw_body: bytes,
    signature: str | None,
    *,
    request_path: str | None = None,
    authorization: str | None = None,
) -> None:
    if not settings.salla_webhook_secret:
        return
    if not signature:
        _log_webhook_401(
            reason="Missing Salla signature",
            request_path=request_path,
            x_salla_signature=signature,
            authorization=authorization,
            signature_validation_passed=False,
            authorization_validation_passed=False,
            line='raise HTTPException(status_code=401, detail="Missing Salla signature")',
        )
        raise HTTPException(status_code=401, detail="Missing Salla signature")

    computed = hmac.new(
        settings.salla_webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, computed):
        _log_webhook_401(
            reason="Invalid Salla signature",
            request_path=request_path,
            x_salla_signature=signature,
            authorization=authorization,
            signature_validation_passed=False,
            authorization_validation_passed=False,
            line='raise HTTPException(status_code=401, detail="Invalid Salla signature")',
        )
        raise HTTPException(status_code=401, detail="Invalid Salla signature")


def verify_salla_token(
    authorization: str | None,
    *,
    request_path: str | None = None,
    x_salla_signature: str | None = None,
    signature_validation_passed: bool = False,
) -> None:
    if not settings.salla_webhook_token:
        return
    if not authorization:
        _log_webhook_401(
            reason="Missing Salla authorization token",
            request_path=request_path,
            x_salla_signature=x_salla_signature,
            authorization=authorization,
            signature_validation_passed=signature_validation_passed,
            authorization_validation_passed=False,
            line='raise HTTPException(status_code=401, detail="Missing Salla authorization token")',
        )
        raise HTTPException(status_code=401, detail="Missing Salla authorization token")

    expected_values = {settings.salla_webhook_token, f"Bearer {settings.salla_webhook_token}"}
    if authorization not in expected_values:
        _log_webhook_401(
            reason="Invalid Salla authorization token",
            request_path=request_path,
            x_salla_signature=x_salla_signature,
            authorization=authorization,
            signature_validation_passed=signature_validation_passed,
            authorization_validation_passed=False,
            line='raise HTTPException(status_code=401, detail="Invalid Salla authorization token")',
        )
        raise HTTPException(status_code=401, detail="Invalid Salla authorization token")


def verify_admin_api_key(api_key: str | None) -> None:
    if not settings.admin_api_key:
        return
    if not api_key or not hmac.compare_digest(api_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid admin API key")
