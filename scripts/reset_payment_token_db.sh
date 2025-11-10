#!/bin/bash
#
# Reset Payment Token Service Database
#
# This script drops and recreates the payment_tokens database schema.
# USE WITH CAUTION: This will delete all data!
#
# Usage:
#   ./scripts/reset_payment_token_db.sh
#
# Environment Variables:
#   DATABASE_URL - PostgreSQL connection URL (optional, defaults to config)
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_DIR="$PROJECT_ROOT/services/payment-token"

echo -e "${YELLOW}Payment Token Service - Database Reset${NC}"
echo "========================================="
echo ""

# Check if we're in the right directory
if [ ! -d "$SERVICE_DIR" ]; then
    echo -e "${RED}Error: Payment token service directory not found at $SERVICE_DIR${NC}"
    exit 1
fi

# Confirmation prompt
echo -e "${RED}WARNING: This will delete all data in the payment_tokens database!${NC}"
read -p "Are you sure you want to continue? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Aborted."
    exit 1
fi

cd "$SERVICE_DIR"

echo -e "${YELLOW}Step 1: Downgrading all migrations...${NC}"
poetry run alembic downgrade base || {
    echo -e "${YELLOW}Note: Downgrade may have failed because tables don't exist yet. Continuing...${NC}"
}

echo ""
echo -e "${YELLOW}Step 2: Upgrading to latest migration (head)...${NC}"
poetry run alembic upgrade head

echo ""
echo -e "${GREEN}✓ Database reset complete!${NC}"
echo ""
echo "Database tables created:"
echo "  - payment_tokens"
echo "  - token_idempotency_keys"
echo "  - encryption_keys"
echo "  - decrypt_audit_log"
echo ""
echo "You can now run integration tests or seed test data."
