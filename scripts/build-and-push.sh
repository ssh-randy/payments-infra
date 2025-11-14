#!/bin/bash
set -e

# Build and push Docker images to AWS ECR
# Usage: ./scripts/build-and-push.sh <service-name> <tag>
# Example: ./scripts/build-and-push.sh payment-token staging-latest

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if required arguments are provided
if [ $# -lt 1 ]; then
    echo -e "${RED}Error: Service name is required${NC}"
    echo "Usage: $0 <service-name> [tag]"
    echo ""
    echo "Available services:"
    echo "  - payment-token"
    echo "  - authorization-api"
    echo "  - auth-processor-worker"
    echo ""
    echo "Example: $0 payment-token staging-latest"
    exit 1
fi

SERVICE=$1
TAG=${2:-staging-latest}
AWS_REGION=${AWS_REGION:-us-east-1}
ENVIRONMENT=${ENVIRONMENT:-staging}

# Validate service name
case $SERVICE in
    payment-token|authorization-api|auth-processor-worker)
        ;;
    *)
        echo -e "${RED}Error: Invalid service name '${SERVICE}'${NC}"
        echo "Valid services: payment-token, authorization-api, auth-processor-worker"
        exit 1
        ;;
esac

# Get AWS account ID
echo -e "${YELLOW}Getting AWS account ID...${NC}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo -e "${RED}Error: Could not determine AWS account ID. Make sure AWS credentials are configured.${NC}"
    exit 1
fi

echo -e "${GREEN}AWS Account ID: ${AWS_ACCOUNT_ID}${NC}"
echo -e "${GREEN}AWS Region: ${AWS_REGION}${NC}"

REPO_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/payments-${ENVIRONMENT}/${SERVICE}"

# Generate protobuf files first
echo -e "${YELLOW}Generating protobuf files...${NC}"
./scripts/generate_protos.sh

# Build the Docker image
echo -e "${YELLOW}Building ${SERVICE}:${TAG}...${NC}"
docker build -f services/${SERVICE}/Dockerfile -t ${SERVICE}:${TAG} .

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Docker build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Build successful${NC}"

# Tag the image for ECR
echo -e "${YELLOW}Tagging image for ECR...${NC}"
docker tag ${SERVICE}:${TAG} ${REPO_URI}:${TAG}

# Also tag as git commit SHA if available
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "")
if [ -n "$GIT_SHA" ]; then
    echo -e "${YELLOW}Also tagging with git SHA: ${GIT_SHA}${NC}"
    docker tag ${SERVICE}:${TAG} ${REPO_URI}:${ENVIRONMENT}-${GIT_SHA}
fi

# Login to ECR
echo -e "${YELLOW}Logging in to ECR...${NC}"
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${REPO_URI}

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: ECR login failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ ECR login successful${NC}"

# Push the image to ECR
echo -e "${YELLOW}Pushing ${REPO_URI}:${TAG} to ECR...${NC}"
docker push ${REPO_URI}:${TAG}

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Docker push failed${NC}"
    exit 1
fi

# Push git SHA tag if available
if [ -n "$GIT_SHA" ]; then
    echo -e "${YELLOW}Pushing ${REPO_URI}:${ENVIRONMENT}-${GIT_SHA} to ECR...${NC}"
    docker push ${REPO_URI}:${ENVIRONMENT}-${GIT_SHA}
fi

echo -e "${GREEN}✓ Successfully pushed ${REPO_URI}:${TAG}${NC}"
if [ -n "$GIT_SHA" ]; then
    echo -e "${GREEN}✓ Successfully pushed ${REPO_URI}:${ENVIRONMENT}-${GIT_SHA}${NC}"
fi

echo ""
echo -e "${GREEN}=== Build and Push Summary ===${NC}"
echo -e "Service: ${SERVICE}"
echo -e "Tag: ${TAG}"
if [ -n "$GIT_SHA" ]; then
    echo -e "Git SHA Tag: ${ENVIRONMENT}-${GIT_SHA}"
fi
echo -e "Repository: ${REPO_URI}"
echo -e "Region: ${AWS_REGION}"
echo ""
echo -e "${GREEN}✓ All done!${NC}"
