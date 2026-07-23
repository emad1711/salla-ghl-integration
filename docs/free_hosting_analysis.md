# Free Hosting Analysis

## Runtime Services Required By This Project

The project is a FastAPI backend that receives Salla webhooks, persists data, and syncs contacts/orders/tags to GoHighLevel.

Required for correct persistence:

- Web service: FastAPI/Uvicorn.
- PostgreSQL-compatible database via `DATABASE_URL`.

Optional but useful:

- Redis queue via `REDIS_URL` and `ENABLE_REDIS=true`.
- Worker process: `python -m salla_ghl.workers.tasks`.
- Scheduler process: `python -m salla_ghl.workers.scheduler`.
- Sentry via `SENTRY_DSN`.

No object/file storage is required. Local SQLite is supported for development, but production should use Postgres because webhook credentials, customer mappings, workflow state, and outbound retries must persist across restarts.

## Free Hosting Comparison

| Provider | No Credit Card | Free Web/API | Free DB | Worker/Cron Free | Fit For This Project |
| --- | --- | --- | --- | --- | --- |
| Render | Yes | Yes, 512 MB RAM / 0.1 CPU | Render Postgres free expires after 30 days | No free background worker/cron | Best no-card web host if paired with external Neon Postgres. |
| Koyeb | Mixed/current docs mention card verification | One free web service: 512 MB RAM / 0.1 vCPU / 2 GB SSD | Free Postgres has active-time limits | Free instances cannot be worker services | Possible, but card/account requirements are less predictable. |
| Fly.io | Trial only without card | Trial only, not permanent | No permanent free DB | No permanent free worker | Not suitable for no-card permanent hosting. |
| Railway | No card for trial | Credit-based, not truly unlimited | Credit-based/trial | No cron on free plan | Good developer experience, but not the safest $0 forever choice. |
| Deta | No | Shut down | Shut down | Shut down | Not available. |
| Oracle Cloud Free Tier | Requires card | Always Free compute | Always Free DB options | Possible on VM | Powerful but violates no-card requirement. |
| PythonAnywhere | Yes | One limited app | SQLite only on new free accounts | Always-on tasks require paid | Not suitable: restricted outbound access can break Salla/GHL APIs. |
| Google Cloud Run | Requires billing/card | Generous free quota | No free managed Postgres without billing | Jobs require billing | Violates no-card requirement. |

## Selected Hosting Provider

Selected web host:

```text
Render Free Web Service
```

Selected database:

```text
Neon Free Postgres
```

Why:

- Both can be started without a credit card.
- Render supports Docker web services and public HTTPS URLs.
- Neon provides persistent Postgres with no 30-day expiration.
- The app can run without Redis because webhook processing falls back to FastAPI background tasks.
- The scheduler can run inline inside the single web container with `RUN_INLINE_SCHEDULER=true`.

## Limitations Of The Selected Free Setup

Render Free Web Service:

- Monthly cost: `$0`.
- Sleep time: spins down after about 15 minutes of no traffic.
- Cold start: can take around 1 minute after sleep.
- RAM: 512 MB.
- CPU: 0.1 CPU.
- Instance count: 1 free web instance.
- Persistent disk: not available on free web services.
- Background workers: paid only.
- Cron jobs: paid, minimum monthly charge.
- Free hours: limited monthly free instance hours; service may suspend if exhausted.

Neon Free Postgres:

- Monthly cost: `$0`.
- Storage: 0.5 GB per project.
- Compute: 100 compute-hours/month.
- Sleep/scale-to-zero: compute suspends when idle and resumes on query.
- Good for low-traffic webhook storage, not high-volume production.

Operational caveat:

- Render sleeping can delay Salla webhook handling on the first request after inactivity.
- Inline scheduler only runs while the web service is awake. Delayed workflow tags/retries may be delayed during sleep.
- For reliable production automation, upgrade later to a paid always-on web service plus separate worker/scheduler.

## Free Database Recommendation

Use Neon Free Postgres.

Set the Render environment variable:

```env
DATABASE_URL=<Neon pooled or direct PostgreSQL connection string>
```

The app automatically normalizes `postgresql://...` to `postgresql+asyncpg://...`.

## Free Render Startup Command

The free single-service startup command is:

```sh
sh scripts/start_web.sh
```

Required Render env flags:

```env
ENABLE_REDIS=false
RUN_INLINE_SCHEDULER=true
RUN_INLINE_WORKER=false
```

## Manual Render Deployment Steps

1. Push this repo to GitHub.
2. Create a Neon Free Postgres database.
3. Copy the Neon `DATABASE_URL`.
4. In Render, create a new Web Service from the GitHub repo.
5. Choose Docker runtime or use the included `render.yaml` Blueprint.
6. Select the Free instance type.
7. Add required environment variables.
8. Deploy.
9. Copy the Render public URL.
10. Set `APP_BASE_URL` to the Render URL and redeploy.
11. Configure Salla:

```text
Store events:
https://<render-service>.onrender.com/webhooks/salla/orders

Authorization event:
https://<render-service>.onrender.com/webhooks/salla/authorize
```

## Required Environment Variables

```env
APP_ENV=production
SERVICE_NAME=salla-ghl-webhook
LOG_LEVEL=INFO
APP_BASE_URL=https://<render-service>.onrender.com
PORT=10000
DATABASE_URL=<neon-postgres-url>
ENABLE_REDIS=false
RUN_INLINE_SCHEDULER=true
RUN_INLINE_WORKER=false

GHL_PRIVATE_INTEGRATION_TOKEN=<required>
GHL_LOCATION_ID=<required>
GHL_BASE_URL=https://services.leadconnectorhq.com
GHL_API_VERSION=2021-07-28
GHL_SOURCE=Salla
GHL_TIMEOUT_SECONDS=20
GHL_PIPELINE_ID=<optional>
GHL_PIPELINE_STAGE_ID=<optional>
GHL_OPPORTUNITY_STATUS=open

SALLA_CLIENT_ID=<required>
SALLA_CLIENT_SECRET=<required>
SALLA_WEBHOOK_SECRET=<required>
SALLA_API_BASE_URL=https://api.salla.dev/admin/v2
SALLA_WEBHOOK_TOKEN=
ADMIN_API_KEY=<required>

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
ENABLE_SENTRY=false
SENTRY_DSN=
```

## Automatic Deployment Decision

Automatic deployment should not run yet because:

- The instruction says not to deploy yet.
- Render deployment requires the user's Render/GitHub account authorization.
- Neon database creation requires a user account and manual secret transfer.
- The free setup is workable, but has sleep and scheduler-delay limitations.

No paid plan is required for the selected setup.
