#!/bin/bash

# Bootstrap Terraform State Backend for Staging Environment
# This script creates the S3 bucket and DynamoDB table required for Terraform state management

set -e

# Configuration
ENVIRONMENT="staging"
AWS_REGION="us-east-1"
S3_BUCKET="sudopay-terraform-state-${ENVIRONMENT}"
DYNAMODB_TABLE="sudopay-terraform-locks-${ENVIRONMENT}"

echo "=========================================="
echo "Bootstrapping Terraform State Backend"
echo "Environment: ${ENVIRONMENT}"
echo "Region: ${AWS_REGION}"
echo "=========================================="

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check AWS credentials
echo "Checking AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "Error: AWS credentials not configured. Please run 'aws configure' first."
    exit 1
fi

echo "AWS Identity verified:"
aws sts get-caller-identity

# Create S3 bucket for Terraform state
echo ""
echo "Creating S3 bucket: ${S3_BUCKET}..."
if aws s3api head-bucket --bucket "${S3_BUCKET}" 2>/dev/null; then
    echo "S3 bucket ${S3_BUCKET} already exists."
else
    # Create bucket
    if [ "${AWS_REGION}" = "us-east-1" ]; then
        # us-east-1 doesn't require LocationConstraint
        aws s3api create-bucket \
            --bucket "${S3_BUCKET}" \
            --region "${AWS_REGION}"
    else
        aws s3api create-bucket \
            --bucket "${S3_BUCKET}" \
            --region "${AWS_REGION}" \
            --create-bucket-configuration LocationConstraint="${AWS_REGION}"
    fi
    echo "S3 bucket created successfully."
fi

# Enable versioning on the S3 bucket
echo "Enabling versioning on S3 bucket..."
aws s3api put-bucket-versioning \
    --bucket "${S3_BUCKET}" \
    --versioning-configuration Status=Enabled

# Enable encryption on the S3 bucket
echo "Enabling server-side encryption on S3 bucket..."
aws s3api put-bucket-encryption \
    --bucket "${S3_BUCKET}" \
    --server-side-encryption-configuration '{
        "Rules": [
            {
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "AES256"
                },
                "BucketKeyEnabled": true
            }
        ]
    }'

# Enable public access block on the S3 bucket
echo "Enabling public access block on S3 bucket..."
aws s3api put-public-access-block \
    --bucket "${S3_BUCKET}" \
    --public-access-block-configuration \
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Create DynamoDB table for state locking
echo ""
echo "Creating DynamoDB table: ${DYNAMODB_TABLE}..."
if aws dynamodb describe-table --table-name "${DYNAMODB_TABLE}" --region "${AWS_REGION}" &>/dev/null; then
    echo "DynamoDB table ${DYNAMODB_TABLE} already exists."
else
    aws dynamodb create-table \
        --table-name "${DYNAMODB_TABLE}" \
        --attribute-definitions AttributeName=LockID,AttributeType=S \
        --key-schema AttributeName=LockID,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "${AWS_REGION}"

    echo "Waiting for DynamoDB table to be active..."
    aws dynamodb wait table-exists \
        --table-name "${DYNAMODB_TABLE}" \
        --region "${AWS_REGION}"

    echo "DynamoDB table created successfully."
fi

echo ""
echo "=========================================="
echo "Bootstrap Complete!"
echo "=========================================="
echo ""
echo "S3 Bucket: ${S3_BUCKET}"
echo "  - Versioning: Enabled"
echo "  - Encryption: AES256"
echo "  - Public Access: Blocked"
echo ""
echo "DynamoDB Table: ${DYNAMODB_TABLE}"
echo "  - Hash Key: LockID"
echo "  - Billing Mode: PAY_PER_REQUEST"
echo ""
echo "Next Steps:"
echo "1. Review the backend configuration in: terraform/environments/staging/backend-config.hcl"
echo "2. Initialize Terraform in your environment directory:"
echo "   cd terraform/environments/staging"
echo "   terraform init -backend-config=backend-config.hcl"
echo ""
