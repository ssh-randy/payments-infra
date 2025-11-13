#!/bin/bash
set -e

echo "=================================================="
echo "Starting Authorization API Service"
echo "=================================================="

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
until PGPASSWORD="${POSTGRES_PASSWORD:-password}" psql -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-payment_events_e2e}" -c '\q' 2>/dev/null; do
  echo "  PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is up!"

# Run database migrations
echo "Running database migrations..."
cd /app/migrations

# Use python -m to run alembic (more reliable than assuming PATH)
python -m alembic upgrade head

cd /app

echo "Migrations complete!"

# Start the application
echo "Starting Authorization API..."
exec uvicorn authorization_api.api.main:app --host 0.0.0.0 --port 8000
