#!/bin/bash
set -e

# Initialize local PostgreSQL databases for development

echo "Setting up local databases..."

# Wait for postgres to be ready
echo "Waiting for PostgreSQL to be ready..."
until docker exec payments-postgres pg_isready -U postgres > /dev/null 2>&1; do
  sleep 1
done

# Create databases
echo "Creating databases..."
docker exec payments-postgres psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'payment_events_db'" | grep -q 1 || docker exec payments-postgres psql -U postgres -c "CREATE DATABASE payment_events_db;"
docker exec payments-postgres psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'payment_tokens_db'" | grep -q 1 || docker exec payments-postgres psql -U postgres -c "CREATE DATABASE payment_tokens_db;"

# Run migrations (placeholder - to be implemented with alembic)
echo "Running migrations..."
# TODO: Add alembic migrations

echo "✓ Local databases initialized successfully"
