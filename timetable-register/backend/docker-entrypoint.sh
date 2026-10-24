#!/bin/sh
set -e

# Apply database migrations
alembic upgrade head

# Optionally load demo data (only if the database is empty)
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python -m app.seed
fi

exec "$@"
