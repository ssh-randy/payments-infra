# Staging Environment - Terraform Configuration

This directory contains Terraform configuration for the staging environment of the payment infrastructure.

## Quick Start

### Prerequisites
- AWS credentials configured (`aws configure` or environment variables)
- Terraform >= 1.0 installed

### Initialize Terraform

```bash
terraform init
```

### Plan Changes

```bash
terraform plan
```

### Apply Configuration

```bash
terraform apply
```

## Current Resources

### ECR Repositories
The ECR module creates container image repositories for:
- `payments-staging/payment-token`
- `payments-staging/authorization-api`
- `payments-staging/auth-processor-worker`

Features:
- Image scanning on push
- AES-256 encryption
- Lifecycle policy (keeps last 10 images)

## Outputs

After applying, view outputs:

```bash
terraform output
```

Available outputs:
- `aws_account_id` - AWS Account ID
- `aws_region` - AWS Region
- `environment` - Environment name
- `ecr_repository_urls` - Map of ECR repository URLs

## Backend Configuration

The backend is configured to use S3 for state storage. To enable:

1. Uncomment the `backend "s3" {}` line in `main.tf`
2. Initialize with backend config:
   ```bash
   terraform init -backend-config=backend-config.hcl
   ```

For local development, the S3 backend is commented out to use local state.

## Next Steps

1. Apply this configuration to create ECR repositories
2. Build and push Docker images (see `/docs/ECR_DEPLOYMENT_GUIDE.md`)
3. Add additional infrastructure modules as needed
