#!/usr/bin/env bash
# Boots a local API on :8000 backed by SQLite, no OAuth wall, seeded + a minted
# session (frontend/e2e/.auth/session.txt). Run by Playwright's webServer.
set -e
cd "$(dirname "$0")/../.."   # repo root
export DATABASE_URL="sqlite:///$(pwd)/e2e.sqlite3"
export REQUIRE_AUTH=False
export DEBUG=True
export SECRET_KEY="e2e-secret-key"
export ALLOWED_HOSTS="localhost,127.0.0.1"
rm -f e2e.sqlite3 frontend/e2e/.auth/session.txt
uv run python manage.py migrate --noinput >/tmp/e2e-migrate.log 2>&1
uv run python manage.py shell -c "exec(open('frontend/e2e/seed.py').read())"
exec uv run uvicorn config.asgi:application --host 127.0.0.1 --port 8000
