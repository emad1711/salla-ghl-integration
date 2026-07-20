import hashlib
import hmac

from fastapi import HTTPException

from salla_ghl.core import security


def test_verify_salla_signature() -> None:
    old_secret = security.settings.salla_webhook_secret
    object.__setattr__(security.settings, "salla_webhook_secret", "secret")
    raw_body = b'{"event":"order.created"}'
    signature = hmac.new(b"secret", raw_body, hashlib.sha256).hexdigest()

    try:
        security.verify_salla_signature(raw_body, signature)
    finally:
        object.__setattr__(security.settings, "salla_webhook_secret", old_secret)


def test_rejects_invalid_salla_signature() -> None:
    old_secret = security.settings.salla_webhook_secret
    object.__setattr__(security.settings, "salla_webhook_secret", "secret")

    try:
        try:
            security.verify_salla_signature(b"{}", "bad")
        except HTTPException:
            return
        raise AssertionError("Expected invalid signature to raise HTTPException")
    finally:
        object.__setattr__(security.settings, "salla_webhook_secret", old_secret)
