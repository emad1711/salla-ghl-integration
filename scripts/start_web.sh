#!/bin/sh
set -eu

if [ "${RUN_INLINE_SCHEDULER:-false}" = "true" ]; then
  python -m salla_ghl.workers.scheduler &
fi

if [ "${RUN_INLINE_WORKER:-false}" = "true" ]; then
  python -m salla_ghl.workers.tasks &
fi

exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8010}"
