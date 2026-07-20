# Salla Production Authorization

This integration no longer depends on ngrok for production. Salla must call permanent HTTPS URLs built from `APP_BASE_URL`.

## Production Endpoints

Set:

```env
APP_BASE_URL=https://your-production-domain.com
```

Configure these Salla URLs:

```text
Store events:
${APP_BASE_URL}/webhooks/salla/orders

Authorization event:
${APP_BASE_URL}/webhooks/salla/authorize
```

The authorization endpoint receives:

```http
POST /webhooks/salla/authorize
Content-Type: application/json
X-Salla-Signature: <hmac-sha256-body-signature>
```

The endpoint validates the same `SALLA_WEBHOOK_SECRET` used by the existing Salla webhooks. It may also validate `Authorization` if `SALLA_WEBHOOK_TOKEN` is configured.

## Expected app.store.authorize Payloads

The endpoint requires:

- `event` equal to `app.store.authorize`, when present.
- `access_token`.
- `store_id`, `merchant`, `merchant_id`, or a nested merchant/store ID.

It accepts these production-safe payload formats.

### Preferred Format

```json
{
  "event": "app.store.authorize",
  "merchant": {
    "id": "123456",
    "name": "Melen"
  },
  "data": {
    "access_token": "ACCESS_TOKEN",
    "refresh_token": "REFRESH_TOKEN",
    "expires_in": 3600
  }
}
```

### Flat Token Format

```json
{
  "event": "app.store.authorize",
  "merchant_id": "123456",
  "merchant_name": "Melen",
  "access_token": "ACCESS_TOKEN",
  "refresh_token": "REFRESH_TOKEN",
  "expires_at": "2026-07-20T21:30:00+00:00"
}
```

### Nested Payload Format

```json
{
  "payload": {
    "event": "app.store.authorize",
    "merchant": {
      "id": "123456",
      "name": "Melen"
    },
    "access_token": "ACCESS_TOKEN",
    "refresh_token": "REFRESH_TOKEN",
    "expires": 3600
  }
}
```

### Nested Authorization Format

```json
{
  "event": "app.store.authorize",
  "data": {
    "store": {
      "id": "123456",
      "name": "Melen"
    },
    "authorization": {
      "access_token": "ACCESS_TOKEN",
      "refresh_token": "REFRESH_TOKEN",
      "expires_in": 3600
    }
  }
}
```

## Response Format

The endpoint never returns token values.

```json
{
  "ok": true,
  "event": "app.store.authorize",
  "store_id": "123456",
  "store_name": "Melen",
  "token_saved": true,
  "expires_at": "2026-07-20T21:30:00+00:00"
}
```

## SQL Migration Output

```sql
CREATE TABLE IF NOT EXISTS salla_integrations (
    id VARCHAR(36) PRIMARY KEY,
    store_id VARCHAR(120) NOT NULL UNIQUE,
    store_name VARCHAR(255),
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_salla_integrations_store_id
    ON salla_integrations (store_id);
```

## salla_integrations Schema

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `VARCHAR(36)` | Yes | Internal UUID primary key. |
| `store_id` | `VARCHAR(120)` | Yes | Salla merchant/store identifier. Unique. |
| `store_name` | `VARCHAR(255)` | No | Merchant/store display name when provided. |
| `access_token` | `TEXT` | Yes | Stored server-side only. Never returned by internal APIs. |
| `refresh_token` | `TEXT` | No | Stored server-side only. Never returned by internal APIs. |
| `expires_at` | `TIMESTAMP WITH TIME ZONE` | No | Calculated from `expires_in` or parsed from `expires_at`/`expires`. |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | Yes | Initial connection timestamp. |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | Yes | Last token update timestamp. |

## Local Authorization Webhook Test

1. Start the app:

```powershell
docker compose up --build
```

2. In another terminal, set the same local webhook secret as the app:

```powershell
$env:APP_BASE_URL="http://localhost:8010"
$env:SALLA_WEBHOOK_SECRET="put_salla_webhook_secret_here"
$env:SALLA_TEST_STORE_ID="123456"
$env:SALLA_TEST_STORE_NAME="Melen"
python scripts/simulate_salla_authorize_webhook.py
```

3. Confirm status without exposing token values:

```powershell
Invoke-RestMethod `
  -Headers @{ "X-Admin-Api-Key" = $env:ADMIN_API_KEY } `
  http://localhost:8010/internal/salla/status
```

## Production Redeploy Steps

1. Regenerate any Salla secrets that were shared outside the Salla dashboard.
2. Deploy this app behind a permanent HTTPS domain.
3. Set production environment variables:

```env
APP_BASE_URL=https://your-production-domain.com
SALLA_CLIENT_ID=<from Salla Partners>
SALLA_CLIENT_SECRET=<from Salla Partners>
SALLA_WEBHOOK_SECRET=<from Salla webhook settings>
ADMIN_API_KEY=<strong internal key>
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
```

4. Start production services:

```powershell
docker compose up --build -d
```

5. Verify health:

```powershell
Invoke-RestMethod https://your-production-domain.com/health
```

6. In Salla Partners, update webhook URLs:

```text
Store events URL:
https://your-production-domain.com/webhooks/salla/orders

Authorization app event URL:
https://your-production-domain.com/webhooks/salla/authorize
```

7. Keep webhook security strategy as `Signature` and use the same value as `SALLA_WEBHOOK_SECRET`.
8. Confirm app scopes include at least:
   - Basic data: read
   - Customers: read
   - Orders: read
   - Carts: read
   - Webhooks: read/write
9. Trigger `app.store.authorize` again using one of the safe methods below.
10. Verify token persistence:

```powershell
Invoke-RestMethod `
  -Headers @{ "X-Admin-Api-Key" = $env:ADMIN_API_KEY } `
  https://your-production-domain.com/internal/salla/status
```

## How to Trigger app.store.authorize Again Safely

Use the least disruptive option available in Salla Partners.

### Option A: Reinstall From Partners For The Same Merchant

Use when the app is still in development or only installed by the Melen merchant.

1. Open Salla Partners.
2. Go to the app.
3. Confirm authentication mode is `Easy`.
4. Confirm the authorization webhook URL is `${APP_BASE_URL}/webhooks/salla/authorize`.
5. Open the target Melen store install/authorization flow from Partners.
6. Authorize the same app again.
7. Salla should emit `app.store.authorize` and the integration will upsert the same `store_id`.

This does not create duplicate records because `store_id` is unique in `salla_integrations`.

### Option B: Ask Store Owner To Reauthorize The Existing App

Use when you do not want to uninstall anything.

1. Keep the current production subscription installed.
2. Ask the merchant to open the installed app authorization/settings page in Salla.
3. Reapprove permissions if Salla shows an authorization prompt.
4. Confirm the `app.store.authorize` event arrives in the Salla webhook log and in `/internal/salla/status`.

This is the safest path if Salla exposes a reauthorization prompt for the installed app.

### Option C: Uninstall And Reinstall During A Short Maintenance Window

Use only if Salla does not expose a reauthorize action.

1. Choose a low-traffic window.
2. Confirm current GHL sync is stable and webhook URLs point to production.
3. Uninstall the Salla app from the Melen store.
4. Immediately reinstall/authorize the same app.
5. Confirm `app.store.authorize` is received.
6. Confirm `/internal/salla/status` shows `connected=true`.

This may briefly pause Salla app webhooks during the uninstall/reinstall window, so prefer Option A or B when possible.

## Current Production Subscription Safety

Changing webhook URLs and receiving a fresh authorization token does not modify existing GoHighLevel data, tags, workflows, opportunities, or customer records. This change only updates where Salla sends events and where the Salla access token is stored.
