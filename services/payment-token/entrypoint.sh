#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting Payment Token Service..."
exec uvicorn payment_token.api.main:app --host 0.0.0.0 --port 8000 --log-level debug --access-log
