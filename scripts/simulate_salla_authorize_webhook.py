"""Send a local app.store.authorize webhook simulation to the FastAPI app.

Usage:
    python scripts/simulate_salla_authorize_webhook.py

Optional environment variables:
    APP_BASE_URL=http://localhost:8010
    SALLA_WEBHOOK_SECRET=local-test-secret
    SALLA_TEST_STORE_ID=123456
    SALLA_TEST_STORE_NAME=Melen
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request


def main() -> None:
    base_url = os.getenv("APP_BASE_URL", "http://localhost:8010").rstrip("/")
    webhook_secret = os.getenv("SALLA_WEBHOOK_SECRET", "")
    payload = {
        "event": "app.store.authorize",
        "merchant": {
            "id": os.getenv("SALLA_TEST_STORE_ID", "123456"),
            "name": os.getenv("SALLA_TEST_STORE_NAME", "Melen"),
        },
        "data": {
            "access_token": os.getenv("SALLA_TEST_ACCESS_TOKEN", "test-access-token"),
            "refresh_token": os.getenv("SALLA_TEST_REFRESH_TOKEN", "test-refresh-token"),
            "expires_in": int(os.getenv("SALLA_TEST_EXPIRES_IN", "3600")),
        },
    }
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if webhook_secret:
        headers["X-Salla-Signature"] = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    request = urllib.request.Request(
        f"{base_url}/webhooks/salla/authorize",
        data=raw_body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            print(response.status)
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.code)
        print(exc.read().decode("utf-8"))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
