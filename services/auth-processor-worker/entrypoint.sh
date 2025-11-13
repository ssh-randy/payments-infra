#!/bin/bash
set -e

echo "Starting Auth Processor Worker..."

# Wait for database to be ready
until pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-postgres}"; do
  echo "Waiting for database..."
  sleep 2
done

echo "Database is ready!"

# Start the worker
exec python -m auth_processor_worker.main
