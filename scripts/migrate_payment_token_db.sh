#!/bin/bash
#
# Run Payment Token Service Database Migrations
#
# This script applies all pending migrations to the payment_tokens database.
#
# Usage:
#   ./scripts/migrate_payment_token_db.sh
#
# Environment Variables:
#   DATABASE_URL - PostgreSQL connection URL (optional, defaults to config)
#

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_DIR="$PROJECT_ROOT/services/payment-token"

echo -e "${YELLOW}Payment Token Service - Database Migration${NC}"
echo "============================================"
echo ""

cd "$SERVICE_DIR"

echo -e "${YELLOW}Applying migrations...${NC}"
poetry run alembic upgrade head

echo ""
echo -e "${GREEN}✓ Migrations applied successfully!${NC}"
