#!/bin/bash
# This script runs inside a container to initialize LocalStack
# It's called automatically by docker-compose

set -e

echo "Waiting for LocalStack to be ready..."
for i in {1..30}; do
  if curl -s http://localstack:4566/_localstack/health | grep -q '"sqs".*"available"'; then
    echo "LocalStack is ready!"
    break
  fi
  echo "  Attempt $i/30..."
  sleep 2
done

echo "Creating SQS FIFO queue for E2E tests..."
aws --endpoint-url=http://localstack:4566 \
    --region=us-east-1 \
    sqs create-queue \
    --queue-name "auth-requests-e2e.fifo" \
    --attributes "FifoQueue=true,ContentBasedDeduplication=false" \
    || echo "  Queue already exists (OK)"

QUEUE_URL=$(aws --endpoint-url=http://localstack:4566 \
    --region=us-east-1 \
    sqs get-queue-url \
    --queue-name "auth-requests-e2e.fifo" \
    --query 'QueueUrl' \
    --output text)

echo "✓ SQS Queue created: $QUEUE_URL"

echo "Creating KMS key for BDK (Base Derivation Key)..."
KEY_OUTPUT=$(aws --endpoint-url=http://localstack:4566 \
    --region=us-east-1 \
    kms create-key \
    --description "E2E test BDK encryption key" \
    --output json 2>&1 || echo '{"KeyMetadata":{"KeyId":"existing"}}')

KEY_ID=$(echo "$KEY_OUTPUT" | grep -o '"KeyId": "[^"]*"' | head -1 | cut -d'"' -f4)

if [ -n "$KEY_ID" ] && [ "$KEY_ID" != "existing" ]; then
    echo "✓ KMS Key created: $KEY_ID"

    # Create alias for the key
    aws --endpoint-url=http://localstack:4566 \
        --region=us-east-1 \
        kms create-alias \
        --alias-name "alias/payment-token-bdk-e2e" \
        --target-key-id "$KEY_ID" \
        || echo "  Alias already exists (OK)"

    echo "✓ KMS Key alias created: alias/payment-token-bdk-e2e"
else
    echo "  KMS key already exists or using existing key"
fi

echo ""
echo "✓ LocalStack initialization complete!"
