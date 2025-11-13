#!/bin/bash
# Initialize LocalStack for E2E tests
# Creates SQS queues and KMS keys needed for testing

set -e

AWS_ENDPOINT=${AWS_ENDPOINT_URL:-http://localhost:4567}
AWS_REGION=${AWS_REGION:-us-east-1}

echo "Initializing LocalStack for E2E tests..."
echo "Endpoint: $AWS_ENDPOINT"
echo "Region: $AWS_REGION"

# Wait for LocalStack to be ready
echo "Waiting for LocalStack..."
max_attempts=30
attempt=0
until curl -s "${AWS_ENDPOINT}/_localstack/health" | grep -q '"sqs".*"available"' || [ $attempt -eq $max_attempts ]; do
    echo "  Attempt $((attempt+1))/$max_attempts..."
    sleep 2
    attempt=$((attempt+1))
done

if [ $attempt -eq $max_attempts ]; then
    echo "ERROR: LocalStack did not become ready in time"
    exit 1
fi

echo "LocalStack is ready!"

# Create FIFO queue for E2E tests
echo "Creating SQS FIFO queue for E2E tests..."
aws --endpoint-url="$AWS_ENDPOINT" \
    --region="$AWS_REGION" \
    sqs create-queue \
    --queue-name "auth-requests-e2e.fifo" \
    --attributes "FifoQueue=true,ContentBasedDeduplication=false" \
    2>/dev/null || echo "  Queue already exists"

# Get queue URL
QUEUE_URL=$(aws --endpoint-url="$AWS_ENDPOINT" \
    --region="$AWS_REGION" \
    sqs get-queue-url \
    --queue-name "auth-requests-e2e.fifo" \
    --query 'QueueUrl' \
    --output text)

echo "  Queue created: $QUEUE_URL"

# Create KMS key for encryption
echo "Creating KMS key..."
KMS_KEY_ID=$(aws --endpoint-url="$AWS_ENDPOINT" \
    --region="$AWS_REGION" \
    kms create-key \
    --description "E2E test encryption key" \
    --query 'KeyMetadata.KeyId' \
    --output text 2>/dev/null) || echo "  Using existing key"

if [ -n "$KMS_KEY_ID" ]; then
    echo "  KMS Key created: $KMS_KEY_ID"
fi

echo ""
echo "✓ LocalStack initialization complete!"
echo ""
echo "Resources created:"
echo "  - SQS Queue: auth-requests-e2e.fifo"
echo "  - Queue URL: $QUEUE_URL"
if [ -n "$KMS_KEY_ID" ]; then
    echo "  - KMS Key: $KMS_KEY_ID"
fi
