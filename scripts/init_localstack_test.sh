#!/bin/bash
set -e

# Initialize LocalStack KMS for e2e tests

echo "Initializing LocalStack KMS for tests..."

AWS_ENDPOINT="${AWS_ENDPOINT:-http://localhost:4566}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Wait for LocalStack KMS to be ready
echo "Waiting for LocalStack KMS..."
until curl -s "$AWS_ENDPOINT/_localstack/health" | grep -q '"kms"'; do
    sleep 2
done
echo "LocalStack KMS is ready"

# Create KMS key for payment token encryption
echo "Creating KMS key for payment token BDK..."
KEY_OUTPUT=$(aws --endpoint-url=$AWS_ENDPOINT \
    --region=$AWS_REGION \
    kms create-key \
    --description "Payment token BDK for e2e tests" \
    2>&1) || true

if echo "$KEY_OUTPUT" | grep -q "KeyId"; then
    KEY_ID=$(echo "$KEY_OUTPUT" | grep -o '"KeyId": "[^"]*"' | head -1 | sed 's/"KeyId": "\(.*\)"/\1/')
    echo "Created KMS key: $KEY_ID"

    # Create alias for the key
    echo "Creating alias 'test-bdk-key'..."
    aws --endpoint-url=$AWS_ENDPOINT \
        --region=$AWS_REGION \
        kms create-alias \
        --alias-name "alias/test-bdk-key" \
        --target-key-id "$KEY_ID" \
        2>&1 || echo "Alias may already exist"

    echo "✓ KMS key and alias created successfully"
else
    echo "Key may already exist, checking alias..."
    aws --endpoint-url=$AWS_ENDPOINT \
        --region=$AWS_REGION \
        kms list-aliases \
        2>&1 | grep -q "test-bdk-key" && echo "✓ Alias exists" || echo "⚠ Alias not found"
fi

echo "✓ LocalStack KMS initialization complete"
