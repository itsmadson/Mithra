#!/usr/bin/env bash
# Start the whole stack for hands-on testing: API, RQ worker, and the web app.
#
# Ctrl-C stops all three. Postgres and Redis are expected to already be running
# (`make up`); this script does not manage them.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv/bin"
API_PORT="${API_PORT:-8010}"
WEB_PORT="${WEB_PORT:-3000}"

export PYTHONPATH="services/api:services/worker:packages/ml"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://bina:bina@localhost:5432/bina}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export NEXT_PUBLIC_API_URL="http://localhost:${API_PORT}"

# The API validates the token's shape at import time, so it needs *a* value to
# boot. Only the worker actually calls Mapillary, so without a real token the
# UI is fully browsable and submitted jobs fail with an explicit auth error
# rather than hanging.
if [ -z "${MAPILLARY_TOKEN:-}" ]; then
  echo "!! MAPILLARY_TOKEN is not set."
  echo "   The UI will work and you can browse existing results, but any job you"
  echo "   submit will fail with an auth error. Get a token at"
  echo "   https://www.mapillary.com/dashboard/developers and re-run with:"
  echo "     MAPILLARY_TOKEN='MLY|...' ./scripts/dev.sh"
  echo
  export MAPILLARY_TOKEN='MLY|nodev|placeholder'
  WORKER_ENABLED=0
else
  WORKER_ENABLED=1
fi

pids=()
cleanup() {
  echo
  echo "==> stopping"
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null; done
  wait 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "==> checking services"
if ! "$VENV/python" -c "
import sys, psycopg
try:
    psycopg.connect('postgresql://bina:bina@localhost:5432/bina').close()
except Exception as exc:
    sys.exit(f'postgres unreachable: {exc}')
"; then
  echo "!! run 'make up' first" >&2
  exit 1
fi

echo "==> api        http://localhost:${API_PORT}/docs"
"$VENV/uvicorn" bina_api.main:app --port "$API_PORT" --reload &
pids+=($!)

if [ "$WORKER_ENABLED" = "1" ]; then
  echo "==> worker     rq"
  "$VENV/rq" worker --url "$REDIS_URL" &
  pids+=($!)
else
  echo "==> worker     skipped (no token)"
fi

echo "==> web        http://localhost:${WEB_PORT}/fa"
(cd apps/web && npm run dev -- --port "$WEB_PORT") &
pids+=($!)

echo
echo "Ready. Open http://localhost:${WEB_PORT}/fa — hold Shift and drag to draw a box."
wait
