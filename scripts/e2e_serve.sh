#!/usr/bin/env bash
# Boot the backend for Playwright e2e against a freshly-seeded, throwaway test
# catalog + license-clean placeholder media (NEVER the real data/catalog.db or
# content/ tree). Serves the built frontend/dist SPA + the /api surface. Auth is
# OFF so the e2e drives the app without a login.
#
# Invoked by frontend/playwright.config.ts webServer. Run `npm run build` in
# frontend/ first so dist is current (the e2e npm script does this).
set -euo pipefail

cd "$(dirname "$0")/.."
DB="${MP_E2E_DB:-${TMPDIR:-/tmp}/mp-e2e-catalog.db}"
PORT="${MP_E2E_PORT:-8788}"
# Throwaway content + thumb-cache roots — isolated from the real library so the
# seed's generated placeholder media never lands in (or reads from) content/.
CONTENT="${MP_E2E_CONTENT:-${TMPDIR:-/tmp}/mp-e2e-content}"
THUMBS="${MP_E2E_THUMBS:-${TMPDIR:-/tmp}/mp-e2e-thumbs}"

# Export CONTENT_ROOT before seeding so the seed writes placeholders where the
# server will later resolve them.
export MEDIA_PIPELINE_CONTENT_ROOT="$CONTENT"
./venv/bin/python scripts/seed_test_catalog.py "$DB"

exec env \
  MEDIA_PIPELINE_DATABASE_PATH="$DB" \
  MEDIA_PIPELINE_PROJECT_ROOT="$PWD" \
  MEDIA_PIPELINE_CONTENT_ROOT="$CONTENT" \
  MEDIA_PIPELINE_THUMBS_DIR="$THUMBS" \
  MEDIA_PIPELINE_AUTH_ENABLED=0 \
  ./venv/bin/uvicorn webui.main:app --port "$PORT" --host 127.0.0.1 --log-level warning
