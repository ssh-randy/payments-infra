#!/bin/bash
set -e

# Reset payment_events_db database (drop and recreate)

echo "⚠️  WARNING: This will DELETE ALL DATA in payment_events_db!"
echo "This is intended for local development only."
echo ""
read -p "Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MIGRATIONS_DIR="$PROJECT_ROOT/infrastructure/migrations"

echo "Resetting payment_events_db..."

# Wait for postgres to be ready
echo "Waiting for PostgreSQL..."
until docker exec payments-postgres pg_isready -U postgres > /dev/null 2>&1; do
  sleep 1
done

# Drop and recreate database
echo "Dropping and recreating database..."
docker exec payments-postgres psql -U postgres -c "DROP DATABASE IF EXISTS payment_events_db;"
docker exec payments-postgres psql -U postgres -c "CREATE DATABASE payment_events_db;"

# Run migrations
echo "Running migrations..."
cd "$MIGRATIONS_DIR"
DATABASE_URL="postgresql://postgres:password@localhost:5432/payment_events_db" \
    poetry run alembic upgrade head

echo "✓ Database reset complete"
