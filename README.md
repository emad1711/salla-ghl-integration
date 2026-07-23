# Salla to GoHighLevel Production Integration

Production-ready FastAPI integration for syncing Salla customers/orders into GoHighLevel, adding lifecycle tags, and triggering CRM workflows.

## Endpoints

- `GET /health`
- `POST /webhooks/salla`
- `POST /webhooks/salla/orders`
- `POST /webhooks/salla/authorize`
- `GET /internal/salla/status`
- `GET /internal/salla/stores`
- `GET /admin/events/{event_id}`
- `POST /admin/events/{event_id}/retry`

Production Salla webhook URLs:

```text
${APP_BASE_URL}/webhooks/salla/orders
${APP_BASE_URL}/webhooks/salla/authorize
```

## Setup

1. Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

2. Edit `.env` and set:

```text
APP_BASE_URL=https://your-production-domain.com
GHL_PRIVATE_INTEGRATION_TOKEN=...
GHL_LOCATION_ID=...
GHL_PIPELINE_ID=...
GHL_PIPELINE_STAGE_ID=...
SALLA_CLIENT_ID=...
SALLA_CLIENT_SECRET=...
SALLA_WEBHOOK_SECRET=...
```

3. Start the service:

```powershell
docker compose up --build
```

4. Configure Salla webhook events:

- `order.created`
- `order.updated`
- `order.status.updated`
- `order.status_changed`
- `order.updated_status`
- `order.completed`
- `order.delivered`
- `order.cancelled`
- `order.canceled`
- `order.refunded`
- `customer.created`
- `customer.registered`
- `customer.created_or_registered`
- `customer.updated`
- `cart.abandoned`
- `abandoned_cart.created`
- `abandoned.cart.created`
- `product.stock.updated`
- `product.quantity.updated`
- `product.updated`

Store events webhook URL:

```text
${APP_BASE_URL}/webhooks/salla/orders
```

App authorization webhook URL:

```text
${APP_BASE_URL}/webhooks/salla/authorize
```

Use the same `SALLA_WEBHOOK_SECRET` value in Salla. Do not use ngrok for production; point Salla to a permanent HTTPS domain backed by your production deployment.

## Salla Authorization Tokens

Salla production Merchant API tokens are persisted when Salla sends the `app.store.authorize` webhook to:

```text
${APP_BASE_URL}/webhooks/salla/authorize
```

The service extracts and stores:

- `access_token`
- `refresh_token`
- store/merchant ID
- store name, when provided
- token expiry, when provided

Tokens are stored in the `salla_integrations` database table and are never returned by API responses.

Check connection status without exposing token values:

```powershell
Invoke-RestMethod `
  -Headers @{ "X-Admin-Api-Key" = $env:ADMIN_API_KEY } `
  http://localhost:8010/internal/salla/status
```

List connected stores:

```powershell
Invoke-RestMethod `
  -Headers @{ "X-Admin-Api-Key" = $env:ADMIN_API_KEY } `
  http://localhost:8010/internal/salla/stores
```

Previous token handling: older code only read `SALLA_API_TOKEN` from the runtime environment in `salla_ghl/core/config.py` and used it in `salla_ghl/integrations/salla/client.py`. There was no database persistence for Salla access or refresh tokens before the `salla_integrations` table.

Full production authorization details, accepted payload examples, SQL schema, local webhook simulation, and safe reauthorization steps are in `docs/salla_production_authorization.md`.

Railway-specific deployment commands and variable setup are in `docs/railway_deployment.md`.

Free-hosting comparison and the selected no-card deployment path are in `docs/free_hosting_analysis.md`.

## Local Health Check

```powershell
Invoke-RestMethod http://localhost:8010/health
```

## Architecture

Services in `docker-compose.yml`:

- `api`: FastAPI webhook and admin API.
- `worker`: Redis-backed webhook processor.
- `scheduler`: delayed workflows, inactive customer checks, outbound retries.
- `postgres`: customer/order/event/workflow store.
- `redis`: queue.

## Production Deployment

1. Deploy the app behind a permanent HTTPS domain.
2. Set `APP_BASE_URL` to that public origin, for example `https://integrations.example.com`.
3. Store secrets as environment variables only:
   - `SALLA_CLIENT_ID`
   - `SALLA_CLIENT_SECRET`
   - `SALLA_WEBHOOK_SECRET`
   - `GHL_PRIVATE_INTEGRATION_TOKEN`
   - `ADMIN_API_KEY`
   - `DATABASE_URL`
   - `REDIS_URL`
4. Start the stack:

```powershell
docker compose up --build -d
```

5. Configure Salla:
   - Authorization/app event URL: `${APP_BASE_URL}/webhooks/salla/authorize`
   - Store events URL: `${APP_BASE_URL}/webhooks/salla/orders`
   - Security strategy: `Signature`
   - Secret: same value as `SALLA_WEBHOOK_SECRET`
6. Install/authorize the Salla app on the production store.
7. Confirm token persistence with `GET /internal/salla/status`.

## GHL Custom Fields

The service can send order metadata to GHL custom fields if you create those fields in GHL and put their IDs in `.env`:

```text
GHL_CF_SALLA_ORDER_ID=
GHL_CF_SALLA_ORDER_TOTAL=
GHL_CF_SALLA_ORDER_STATUS=
GHL_CF_SALLA_ORDER_ADMIN_URL=
GHL_CF_SALLA_PAYMENT_METHOD=
GHL_CF_SALLA_PRODUCTS=
GHL_CF_SALLA_LAST_EVENT=
GHL_CF_SALLA_LAST_ORDER_AT=
GHL_CF_SALLA_TOTAL_SPENT=
GHL_CF_SALLA_PURCHASE_COUNT=
GHL_CF_SALLA_LAST_PURCHASE_AT=
GHL_CF_SALLA_LOYALTY_POINTS=
```

Leave them empty if you only want to create/update the contact.

## GHL Pipeline

Set these IDs to create or update a real GoHighLevel opportunity for every `order.created` event:

```text
GHL_PIPELINE_ID=
GHL_PIPELINE_STAGE_ID=
GHL_OPPORTUNITY_STATUS=open
```

The opportunity is linked to the synced GHL contact and uses the Salla order total as `monetaryValue`.

## Loyalty Points

Points are calculated from eligible revenue and order count, then sent to `GHL_CF_SALLA_LOYALTY_POINTS`:

```text
LOYALTY_POINTS_PER_CURRENCY_UNIT=1
LOYALTY_POINTS_PER_ORDER=0
LOYALTY_ELIGIBLE_STATUSES=created,paid,completed,delivered
```

Cancelled, canceled, and refunded orders do not count unless you explicitly add their status to `LOYALTY_ELIGIBLE_STATUSES`.

## GHL Workflow Tags

Every accepted Salla order webhook sends tags that can trigger Go High Level workflows:

```text
salla
salla-order
order.created
order.updated
salla-status-STATUS
salla-product-SKU_OR_NAME
salla-vip-customer
salla-new-customer
salla-returning-customer
salla-inactive-customer
salla-post-purchase
salla-review-request-due
salla-order-status-updated
salla-shipping-update
salla-stop-cross-sell
salla-cart-abandoned
salla-customer-created
salla-welcome-campaign
salla-product-stock-updated
salla-back-in-stock
salla-winback-due
```

Set `GHL_VIP_ORDER_TOTAL_THRESHOLD` in `.env` to control when `salla-vip-customer` is added.

## Workflows

GoHighLevel workflows should trigger on tags:

- Abandoned cart: `salla-cart-abandoned`, `salla-cart-abandoned-stage-1`, `salla-cart-abandoned-stage-2`.
- Post purchase: `salla-post-purchase`, `salla-order-paid`.
- Order status updates: `salla-order-status-updated`, `salla-shipping-update`.
- Cancelled/refunded orders: `salla-stop-cross-sell`.
- New customers: `salla-customer-created`, `salla-welcome-campaign`.
- Back in stock: `salla-product-stock-updated`, `salla-back-in-stock`.
- Product-specific back in stock: `salla-back-in-stock-SKU_OR_NAME` for customers who had that product in an abandoned cart.
- Review request: `salla-review-request-due`.
- Win-back: `salla-winback-due`.
- Segmentation: `salla-vip-customer`, `salla-new-customer`, `salla-returning-customer`, `salla-inactive-customer`.

## Testing

```powershell
python -m compileall app.py salla_ghl
pytest
```

## Production Checklist

- Configure real `DATABASE_URL` and `REDIS_URL`.
- Keep secrets in environment variables only.
- Confirm Salla production store webhooks are active.
- Confirm `GET /health` is healthy through the public URL.
- Create GHL workflows for the tags above.
- Configure uptime monitoring and Sentry/alerting if needed.
- Test a real Salla order and verify contact/tags in GoHighLevel.
