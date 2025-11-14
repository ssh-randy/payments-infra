# ECR Deployment Guide

This guide explains how to build and deploy Docker images to AWS ECR for the payment infrastructure services.

## Prerequisites

1. **AWS CLI** installed and configured with appropriate credentials
2. **Docker** installed and running
3. **Terraform** installed (>= 1.0)
4. **AWS Permissions** required:
   - ECR: CreateRepository, PutLifecyclePolicy, PutImageScanningConfiguration
   - IAM: GetUser (for account ID)

## Step 1: Configure AWS Credentials

Ensure your AWS credentials are configured:

```bash
aws configure
# Or set environment variables:
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_REGION=us-east-1
```

## Step 2: Create ECR Repositories with Terraform

Navigate to the staging environment and apply Terraform:

```bash
cd terraform/environments/staging
terraform init
terraform plan
terraform apply
```

This will create three ECR repositories:
- `payments-staging/payment-token`
- `payments-staging/authorization-api`
- `payments-staging/auth-processor-worker`

The repositories will have:
- Image scanning enabled
- AES-256 encryption
- Lifecycle policy (keep last 10 images)

## Step 3: Build and Push Docker Images

### Option A: Build and Push All Services

Use the convenience script to build and push all services at once:

```bash
./scripts/build-and-push-all.sh staging-latest
```

### Option B: Build and Push Individual Services

Build and push services one at a time:

```bash
# Payment Token Service
./scripts/build-and-push.sh payment-token staging-latest

# Authorization API
./scripts/build-and-push.sh authorization-api staging-latest

# Auth Processor Worker
./scripts/build-and-push.sh auth-processor-worker staging-latest
```

## Step 4: Verify Images

Check that images were pushed successfully:

```bash
# List images in a repository
aws ecr list-images --repository-name payments-staging/payment-token --region us-east-1

# Describe images to see tags and scan results
aws ecr describe-images --repository-name payments-staging/payment-token --region us-east-1
```

## Step 5: Pull and Test Images (Optional)

Pull an image from ECR to verify:

```bash
# Get your AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com

# Pull image
docker pull ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/payments-staging/payment-token:staging-latest

# Run image to test
docker run -p 8000:8000 ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/payments-staging/payment-token:staging-latest
```

## Image Tagging Strategy

The build script automatically creates multiple tags for each image:

1. **Specified tag** (e.g., `staging-latest`) - The tag you provide
2. **Git SHA tag** (e.g., `staging-a1b2c3d`) - Automatically tagged with current git commit

This allows you to:
- Use `staging-latest` for always pulling the most recent image
- Use git SHA tags for reproducible deployments and rollbacks

## Security Scanning

Images are automatically scanned for vulnerabilities when pushed to ECR. To view scan results:

```bash
aws ecr describe-image-scan-findings \
  --repository-name payments-staging/payment-token \
  --image-id imageTag=staging-latest \
  --region us-east-1
```

## Troubleshooting

### Build Fails: Protobuf Files Missing

The build script automatically generates protobuf files, but if you see errors:

```bash
./scripts/generate_protos.sh
```

### ECR Login Fails

Ensure your AWS credentials are configured and have ECR permissions:

```bash
aws sts get-caller-identity
```

### Image Push Fails: Repository Does Not Exist

Make sure you've created the ECR repositories with Terraform first:

```bash
cd terraform/environments/staging
terraform apply
```

### Docker Build Fails: Out of Disk Space

Clean up old Docker images:

```bash
docker system prune -a
```

## Repository URLs

After creating repositories, Terraform will output the repository URLs:

```bash
cd terraform/environments/staging
terraform output ecr_repository_urls
```

## Cost Considerations

- **Storage**: ~$0.10/GB/month
- **Data transfer**: Charged for data transferred out of ECR
- **Lifecycle policies**: Keep last 10 images to control costs

For staging environment, expect < $5/month in ECR costs.

## Next Steps

After images are pushed to ECR:
1. Update ECS task definitions to reference these image URIs
2. Deploy services to ECS
3. Set up CI/CD pipeline to automate image builds on git push
