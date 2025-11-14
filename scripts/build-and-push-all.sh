#!/bin/bash
set -e

# Build and push all services to ECR
# Usage: ./scripts/build-and-push-all.sh [tag]
# Example: ./scripts/build-and-push-all.sh staging-latest

TAG=${1:-staging-latest}

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Building and pushing all services to ECR${NC}"
echo -e "${YELLOW}Tag: ${TAG}${NC}"
echo ""

SERVICES=("payment-token" "authorization-api" "auth-processor-worker")

for SERVICE in "${SERVICES[@]}"; do
    echo -e "${YELLOW}=== Building and pushing ${SERVICE} ===${NC}"
    ./scripts/build-and-push.sh ${SERVICE} ${TAG}
    echo ""
done

echo -e "${GREEN}✓ All services built and pushed successfully!${NC}"
