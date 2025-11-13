# Terraform State Backend Bootstrap

This directory contains scripts to bootstrap the Terraform state backend infrastructure.

## Overview

Before you can use Terraform to manage your infrastructure, you need to set up a backend to store the Terraform state. This is a "chicken and egg" problem - you need infrastructure to manage infrastructure state.

The bootstrap process creates:
1. An S3 bucket for storing Terraform state files
2. A DynamoDB table for state locking

These resources are created manually (via AWS CLI) so they can then be used to store state for all other infrastructure.

## Quick Start

### Prerequisites

- AWS CLI installed and configured
- AWS credentials with permissions to create S3 buckets and DynamoDB tables
- Bash shell (macOS, Linux, or WSL on Windows)

### Run the Bootstrap Script

```bash
./bootstrap-state-backend.sh
```

The script will:
1. Verify AWS CLI is installed and credentials are configured
2. Create the S3 bucket with versioning and encryption enabled
3. Create the DynamoDB table for state locking
4. Display a summary of created resources

### Expected Output

```
==========================================
Bootstrapping Terraform State Backend
Environment: staging
Region: us-east-1
==========================================

AWS Identity verified:
{
    "UserId": "...",
    "Account": "...",
    "Arn": "..."
}

Creating S3 bucket: sudopay-terraform-state-staging...
S3 bucket created successfully.
Enabling versioning on S3 bucket...
Enabling server-side encryption on S3 bucket...
Enabling public access block on S3 bucket...

Creating DynamoDB table: sudopay-terraform-locks-staging...
Waiting for DynamoDB table to be active...
DynamoDB table created successfully.

==========================================
Bootstrap Complete!
==========================================

S3 Bucket: sudopay-terraform-state-staging
  - Versioning: Enabled
  - Encryption: AES256
  - Public Access: Blocked

DynamoDB Table: sudopay-terraform-locks-staging
  - Hash Key: LockID
  - Billing Mode: PAY_PER_REQUEST
```

## What Gets Created

### S3 Bucket

- **Name**: `sudopay-terraform-state-staging`
- **Purpose**: Stores Terraform state files
- **Features**:
  - Versioning enabled (allows recovery of previous states)
  - Server-side encryption with AES256
  - Public access blocked (security best practice)
- **Region**: `us-east-1`

### DynamoDB Table

- **Name**: `sudopay-terraform-locks-staging`
- **Purpose**: Provides state locking to prevent concurrent modifications
- **Schema**:
  - Hash Key: `LockID` (String)
- **Billing**: PAY_PER_REQUEST (only pay for what you use)
- **Region**: `us-east-1`

## Verification

After running the bootstrap script, verify the resources were created:

```bash
# Check S3 bucket
aws s3 ls | grep sudopay-terraform-state

# Check S3 bucket versioning
aws s3api get-bucket-versioning --bucket sudopay-terraform-state-staging

# Check S3 bucket encryption
aws s3api get-bucket-encryption --bucket sudopay-terraform-state-staging

# Check DynamoDB table
aws dynamodb describe-table --table-name sudopay-terraform-locks-staging
```

## Next Steps

After bootstrapping the state backend:

1. Navigate to the environment directory:
   ```bash
   cd ../environments/staging
   ```

2. Initialize Terraform with the backend configuration:
   ```bash
   terraform init -backend-config=backend-config.hcl
   ```

3. Validate the configuration:
   ```bash
   terraform validate
   terraform plan
   ```

4. Begin deploying infrastructure!

## Idempotency

The bootstrap script is idempotent - you can run it multiple times safely. If resources already exist, the script will detect them and skip creation.

## Cleanup (⚠️ Dangerous)

To delete the state backend resources (use with extreme caution):

```bash
# Delete S3 bucket (must be empty first)
aws s3 rb s3://sudopay-terraform-state-staging --force

# Delete DynamoDB table
aws dynamodb delete-table --table-name sudopay-terraform-locks-staging
```

**Warning**: Deleting these resources will destroy all Terraform state. Only do this if you're tearing down the entire environment and have backups.

## Troubleshooting

### AWS CLI not found

Install the AWS CLI:
- macOS: `brew install awscli`
- Linux: Download from https://aws.amazon.com/cli/
- Windows: Download installer from AWS website

### Credentials not configured

Configure AWS credentials:
```bash
aws configure
```

Or set environment variables:
```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-1"
```

### Permission denied errors

Ensure your AWS user/role has the following permissions:
- `s3:CreateBucket`
- `s3:PutBucketVersioning`
- `s3:PutBucketEncryption`
- `s3:PutPublicAccessBlock`
- `dynamodb:CreateTable`
- `dynamodb:DescribeTable`

### Bucket name already taken

S3 bucket names are globally unique. If the bucket name is taken, modify the script to use a different name:
```bash
S3_BUCKET="sudopay-terraform-state-${ENVIRONMENT}-${RANDOM_SUFFIX}"
```

## Additional Environments

To create state backend for other environments (production, dev, etc.), modify the script variables:

```bash
ENVIRONMENT="production"
```

Or create separate scripts for each environment.
