#!/bin/bash
set -e

# Run Alembic migrations for payment_events_db

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MIGRATIONS_DIR="$PROJECT_ROOT/infrastructure/migrations"

echo "Running migrations for payment_events_db..."

# Default database URL (can be overridden by environment variable)
: "${DATABASE_URL:=postgresql://postgres:password@localhost:5432/payment_events_db}"

export DATABASE_URL

cd "$MIGRATIONS_DIR"

# Run migrations
poetry run alembic upgrade head

echo "✓ Migrations completed successfully"
