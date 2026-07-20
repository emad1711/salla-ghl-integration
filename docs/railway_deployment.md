# Railway Deployment

This project is ready to deploy as a Dockerfile-based Railway service.

## Files Used By Railway

- `Dockerfile`
- `railway.json`
- `.dockerignore`
- `.env.example`

Railway injects `PORT`; the Dockerfile and `railway.json` both start Uvicorn with that port.

## Required Railway Variables

Set these on the app service:

```env
APP_ENV=production
SERVICE_NAME=salla-ghl-webhook
LOG_LEVEL=INFO
APP_BASE_URL=https://<your-railway-domain>
ENABLE_REDIS=false

DATABASE_URL=${{Postgres.DATABASE_URL}}

GHL_PRIVATE_INTEGRATION_TOKEN=<ghl-private-integration-token>
GHL_LOCATION_ID=<ghl-location-id>
GHL_BASE_URL=https://services.leadconnectorhq.com
GHL_API_VERSION=2021-07-28
GHL_SOURCE=Salla
GHL_TIMEOUT_SECONDS=20
GHL_PIPELINE_ID=<optional-pipeline-id>
GHL_PIPELINE_STAGE_ID=<optional-stage-id>
GHL_OPPORTUNITY_STATUS=open

SALLA_CLIENT_ID=<salla-client-id>
SALLA_CLIENT_SECRET=<salla-client-secret>
SALLA_WEBHOOK_SECRET=<salla-webhook-secret>
SALLA_API_BASE_URL=https://api.salla.dev/admin/v2
SALLA_WEBHOOK_TOKEN=

ADMIN_API_KEY=<strong-internal-admin-key>
ENABLE_SENTRY=false
SENTRY_DSN=

SALLA_ALLOWED_EVENTS=order.created,order.updated,order.status.updated,order.completed,order.delivered,order.cancelled,order.refunded,order.canceled,order.status_changed,order.updated_status,customer.created,customer.registered,customer.updated,customer.created_or_registered,abandoned.cart,abandoned.cart.status.changed,abandoned.cart.purchased,cart.abandoned,abandoned_cart.created,abandoned.cart.created,product.stock.updated,product.quantity.updated,product.updated

VIP_TOTAL_SPENT_THRESHOLD=1000
LOYALTY_POINTS_PER_CURRENCY_UNIT=1
LOYALTY_POINTS_PER_ORDER=0
LOYALTY_ELIGIBLE_STATUSES=created,paid,completed,delivered
INACTIVE_DAYS_THRESHOLD=60
REVIEW_REQUEST_DELAY_HOURS=48
ABANDONED_CART_DELAYS_MINUTES=30,1440,2880
MAX_RETRY_ATTEMPTS=5
RETRY_BASE_DELAY_SECONDS=30
```

Set `ENABLE_REDIS=true` and add a Redis plugin/service only if you want Redis-backed background processing on Railway. With `ENABLE_REDIS=false`, FastAPI background tasks still process incoming webhooks.

## Exact Railway CLI Commands

Install and login:

```powershell
npm install -g @railway/cli
railway login
```

From the project folder:

```powershell
cd "C:\Users\mohamed\OneDrive\Desktop\salla"
railway init
railway add --database postgres
railway variable set APP_ENV=production
railway variable set SERVICE_NAME=salla-ghl-webhook
railway variable set LOG_LEVEL=INFO
railway variable set ENABLE_REDIS=false
railway variable set GHL_BASE_URL=https://services.leadconnectorhq.com
railway variable set GHL_API_VERSION=2021-07-28
railway variable set GHL_SOURCE=Salla
railway variable set GHL_TIMEOUT_SECONDS=20
railway variable set GHL_OPPORTUNITY_STATUS=open
railway variable set SALLA_API_BASE_URL=https://api.salla.dev/admin/v2
railway variable set ENABLE_SENTRY=false
railway variable set VIP_TOTAL_SPENT_THRESHOLD=1000
railway variable set LOYALTY_POINTS_PER_CURRENCY_UNIT=1
railway variable set LOYALTY_POINTS_PER_ORDER=0
railway variable set LOYALTY_ELIGIBLE_STATUSES=created,paid,completed,delivered
railway variable set INACTIVE_DAYS_THRESHOLD=60
railway variable set REVIEW_REQUEST_DELAY_HOURS=48
railway variable set ABANDONED_CART_DELAYS_MINUTES=30,1440,2880
railway variable set MAX_RETRY_ATTEMPTS=5
railway variable set RETRY_BASE_DELAY_SECONDS=30
railway variable set SALLA_ALLOWED_EVENTS=order.created,order.updated,order.status.updated,order.completed,order.delivered,order.cancelled,order.refunded,order.canceled,order.status_changed,order.updated_status,customer.created,customer.registered,customer.updated,customer.created_or_registered,abandoned.cart,abandoned.cart.status.changed,abandoned.cart.purchased,cart.abandoned,abandoned_cart.created,abandoned.cart.created,product.stock.updated,product.quantity.updated,product.updated
```

Set real secrets interactively or paste values carefully:

```powershell
railway variable set APP_BASE_URL=https://<your-railway-domain>
railway variable set GHL_PRIVATE_INTEGRATION_TOKEN=<value>
railway variable set GHL_LOCATION_ID=<value>
railway variable set GHL_PIPELINE_ID=<value>
railway variable set GHL_PIPELINE_STAGE_ID=<value>
railway variable set SALLA_CLIENT_ID=<value>
railway variable set SALLA_CLIENT_SECRET=<value>
railway variable set SALLA_WEBHOOK_SECRET=<value>
railway variable set ADMIN_API_KEY=<value>
```

Deploy and generate a public Railway URL:

```powershell
railway up
railway domain
railway domain list
```

After Railway prints the public domain, set:

```powershell
railway variable set APP_BASE_URL=https://<generated-domain>
railway redeploy
```

## Salla URLs After Deployment

Configure Salla Partners with:

```text
Store events URL:
https://<generated-domain>/webhooks/salla/orders

Authorization event URL:
https://<generated-domain>/webhooks/salla/authorize
```

Check deployment:

```powershell
Invoke-RestMethod https://<generated-domain>/health
Invoke-RestMethod `
  -Headers @{ "X-Admin-Api-Key" = "<ADMIN_API_KEY>" } `
  https://<generated-domain>/internal/salla/status
```
