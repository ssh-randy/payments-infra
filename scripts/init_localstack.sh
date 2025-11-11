#!/bin/bash
set -e

# Initialize LocalStack with SQS queues for payment processing

echo "Initializing LocalStack (SQS queues)..."

# Wait for LocalStack to be ready
until curl -s http://localhost:4566/_localstack/health | grep -q '"sqs": "available"'; do
    echo "Waiting for LocalStack SQS..."
    sleep 2
done

AWS_ENDPOINT="http://localhost:4566"
AWS_REGION="us-east-1"

# Create Auth Request Queue (FIFO)
echo "Creating payment-auth-requests.fifo queue..."
aws --endpoint-url=$AWS_ENDPOINT \
    --region=$AWS_REGION \
    sqs create-queue \
    --queue-name payment-auth-requests.fifo \
    --attributes '{
        "FifoQueue": "true",
        "ContentBasedDeduplication": "false",
        "MessageRetentionPeriod": "345600",
        "VisibilityTimeout": "30",
        "ReceiveMessageWaitTimeSeconds": "20"
    }' \
    || echo "Queue already exists"

# Create Auth Request DLQ (FIFO)
echo "Creating payment-auth-requests-dlq.fifo queue..."
aws --endpoint-url=$AWS_ENDPOINT \
    --region=$AWS_REGION \
    sqs create-queue \
    --queue-name payment-auth-requests-dlq.fifo \
    --attributes '{
        "FifoQueue": "true",
        "ContentBasedDeduplication": "false",
        "MessageRetentionPeriod": "1209600"
    }' \
    || echo "Queue already exists"

# Create Void Request Queue (Standard)
echo "Creating payment-void-requests queue..."
aws --endpoint-url=$AWS_ENDPOINT \
    --region=$AWS_REGION \
    sqs create-queue \
    --queue-name payment-void-requests \
    --attributes '{
        "MessageRetentionPeriod": "1209600",
        "VisibilityTimeout": "60",
        "ReceiveMessageWaitTimeSeconds": "20"
    }' \
    || echo "Queue already exists"

# Create Void Request DLQ (Standard)
echo "Creating payment-void-requests-dlq queue..."
aws --endpoint-url=$AWS_ENDPOINT \
    --region=$AWS_REGION \
    sqs create-queue \
    --queue-name payment-void-requests-dlq \
    --attributes '{
        "MessageRetentionPeriod": "1209600"
    }' \
    || echo "Queue already exists"

# Create KMS key for token encryption (placeholder)
echo "Creating KMS key for payment token encryption..."
KEY_OUTPUT=$(aws --endpoint-url=$AWS_ENDPOINT \
    --region=$AWS_REGION \
    kms create-key \
    --description "Payment token BDK for local dev" \
    2>&1) || echo "KMS key may already exist"

if echo "$KEY_OUTPUT" | grep -q "KeyId"; then
    KEY_ID=$(echo "$KEY_OUTPUT" | grep -o '"KeyId": "[^"]*"' | sed 's/"KeyId": "\(.*\)"/\1/')
    echo "Created KMS key: $KEY_ID"

    # Create alias for the key
    echo "Creating alias 'test-bdk-key'..."
    aws --endpoint-url=$AWS_ENDPOINT \
        --region=$AWS_REGION \
        kms create-alias \
        --alias-name "alias/test-bdk-key" \
        --target-key-id "$KEY_ID" \
        || echo "Alias may already exist"
fi

echo "✓ LocalStack initialization complete"
echo ""
echo "Available SQS queues:"
aws --endpoint-url=$AWS_ENDPOINT --region=$AWS_REGION sqs list-queues
