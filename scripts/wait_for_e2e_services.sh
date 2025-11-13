#!/bin/bash
# Wait for all E2E services to be healthy before running tests

set -e

# Configuration
MAX_WAIT=120  # Maximum wait time in seconds
CHECK_INTERVAL=2  # Seconds between health checks

# Service health check URLs
AUTHORIZATION_API="http://localhost:8000/health"
PAYMENT_TOKEN_SERVICE="http://localhost:8001/health"
LOCALSTACK="http://localhost:4567/_localstack/health"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "Waiting for E2E services to be healthy..."
echo "=================================================="
echo ""

# Function to check if a service is healthy
check_service() {
    local name=$1
    local url=$2
    local start_time=$(date +%s)

    echo -n "Checking $name..."

    while true; do
        # Check if we've exceeded max wait time
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        if [ $elapsed -ge $MAX_WAIT ]; then
            echo -e " ${RED}✗ TIMEOUT${NC}"
            echo "  Service did not become healthy within ${MAX_WAIT}s"
            return 1
        fi

        # Try to reach the service
        if curl -s -f "$url" > /dev/null 2>&1; then
            echo -e " ${GREEN}✓ HEALTHY${NC}"
            return 0
        fi

        # Wait before next check
        sleep $CHECK_INTERVAL
        echo -n "."
    done
}

# Check PostgreSQL (main database)
echo -n "Checking PostgreSQL (main)..."
pg_start=$(date +%s)
while ! PGPASSWORD=password psql -h localhost -p 5434 -U postgres -d payment_events_e2e -c "SELECT 1" > /dev/null 2>&1; do
    pg_current=$(date +%s)
    pg_elapsed=$((pg_current - pg_start))
    if [ $pg_elapsed -ge $MAX_WAIT ]; then
        echo -e " ${RED}✗ TIMEOUT${NC}"
        echo "  PostgreSQL did not become ready within ${MAX_WAIT}s"
        exit 1
    fi
    sleep $CHECK_INTERVAL
    echo -n "."
done
echo -e " ${GREEN}✓ HEALTHY${NC}"

# Check PostgreSQL (tokens database)
echo -n "Checking PostgreSQL (tokens)..."
pgt_start=$(date +%s)
while ! PGPASSWORD=password psql -h localhost -p 5435 -U postgres -d payment_tokens_e2e -c "SELECT 1" > /dev/null 2>&1; do
    pgt_current=$(date +%s)
    pgt_elapsed=$((pgt_current - pgt_start))
    if [ $pgt_elapsed -ge $MAX_WAIT ]; then
        echo -e " ${RED}✗ TIMEOUT${NC}"
        echo "  PostgreSQL (tokens) did not become ready within ${MAX_WAIT}s"
        exit 1
    fi
    sleep $CHECK_INTERVAL
    echo -n "."
done
echo -e " ${GREEN}✓ HEALTHY${NC}"

# Check LocalStack
check_service "LocalStack" "$LOCALSTACK" || exit 1

# Check Payment Token Service
check_service "Payment Token Service" "$PAYMENT_TOKEN_SERVICE" || exit 1

# Check Authorization API
check_service "Authorization API" "$AUTHORIZATION_API" || exit 1

echo ""
echo "=================================================="
echo -e "${GREEN}All services are healthy!${NC}"
echo "=================================================="
echo ""
echo "Service endpoints:"
echo "  - Authorization API:      http://localhost:8000"
echo "  - Payment Token Service:  http://localhost:8001"
echo "  - PostgreSQL (main):      localhost:5434"
echo "  - PostgreSQL (tokens):    localhost:5435"
echo "  - LocalStack:             http://localhost:4567"
echo ""
echo "Ready to run E2E tests!"
echo ""

exit 0
