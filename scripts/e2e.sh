#!/usr/bin/env bash
# Run the browser suite against real servers.
#
# This lives in a script rather than a Makefile recipe because Make runs every
# recipe line in its own shell: a server backgrounded on one line is dead by the
# next line, and the tests then fail against nothing.
#
# The database is seeded with a finished job so the run never depends on
# Mapillary, a token, or network reachability. The token below only has to
# satisfy config validation — the worker is not part of this run, so no
# Mapillary call is made.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv/bin"
API_PORT="${API_PORT:-8020}"
WEB_PORT="${WEB_PORT:-3100}"

export PYTHONPATH="services/api:services/worker:packages/ml"
export MAPILLARY_TOKEN="${MAPILLARY_TOKEN:-MLY|e2e|placeholder}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://bina:bina@localhost:5434/bina}"
export NEXT_PUBLIC_API_URL="http://localhost:${API_PORT}"

api_pid=""
web_pid=""

# Kill whole process groups, not the direct children. `npm run start` execs a
# shell that spawns next-server, so killing the pid we captured left the real
# server holding the port; the following run then bound nothing and silently
# tested the previous build.
cleanup() {
  for pid in "$api_pid" "$web_pid"; do
    [ -n "$pid" ] || continue
    kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

echo "==> seeding"
"$VENV/python" tests/e2e/seed.py

echo "==> building web"
(cd apps/web && npm run build >/dev/null)

echo "==> starting api on :${API_PORT}"
setsid "$VENV/uvicorn" bina_api.main:app --port "$API_PORT" >/tmp/bina-e2e-api.log 2>&1 &
api_pid=$!

echo "==> starting web on :${WEB_PORT}"
setsid bash -c "cd apps/web && npm run start -- --port $WEB_PORT" >/tmp/bina-e2e-web.log 2>&1 &
web_pid=$!

wait_for() {
  local url=$1 name=$2
  for _ in $(seq 1 60); do
    if curl -sf -o /dev/null --max-time 2 "$url"; then
      echo "==> $name ready"
      return 0
    fi
    sleep 1
  done
  echo "!! $name never became ready at $url" >&2
  return 1
}

wait_for "http://localhost:${API_PORT}/api/health" "api"
wait_for "http://localhost:${WEB_PORT}/fa" "web"

echo "==> running playwright"
cd tests/e2e && npx playwright test "$@"
