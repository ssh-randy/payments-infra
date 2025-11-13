# SudoPay Infrastructure - Terraform

This directory contains Infrastructure as Code (IaC) for the SudoPay payment processing platform using Terraform.

## Directory Structure

```
terraform/
├── bootstrap/                    # Bootstrap scripts for initial setup
│   └── bootstrap-state-backend.sh
├── environments/                 # Environment-specific configurations
│   └── staging/
│       ├── backend-config.hcl   # S3 backend configuration
│       ├── main.tf              # Main Terraform configuration
│       └── variables.tf         # Environment variables
└── modules/                     # Reusable Terraform modules
```

## Prerequisites

- [Terraform](https://www.terraform.io/downloads.html) >= 1.0
- [AWS CLI](https://aws.amazon.com/cli/) configured with appropriate credentials
- AWS account with permissions to create:
  - S3 buckets
  - DynamoDB tables
  - VPC and networking resources
  - RDS instances
  - ECS clusters and services
  - IAM roles and policies

## Getting Started

### 1. Bootstrap the Terraform State Backend

Before deploying any infrastructure, you need to set up the Terraform state backend. This creates an S3 bucket for state storage and a DynamoDB table for state locking.

```bash
# From the terraform directory
cd bootstrap
./bootstrap-state-backend.sh
```

This script will create:
- **S3 Bucket**: `sudopay-terraform-state-staging`
  - Versioning enabled for state recovery
  - AES256 encryption at rest
  - Public access blocked
- **DynamoDB Table**: `sudopay-terraform-locks-staging`
  - Used for state locking to prevent concurrent modifications
  - PAY_PER_REQUEST billing mode

### 2. Initialize Terraform

After bootstrapping the state backend, initialize Terraform in the staging environment:

```bash
cd environments/staging
terraform init -backend-config=backend-config.hcl
```

This command will:
- Download required provider plugins (AWS)
- Configure the S3 backend for state storage
- Set up state locking with DynamoDB

### 3. Validate the Configuration

Verify that Terraform can connect to AWS and the backend is configured correctly:

```bash
terraform validate
terraform plan
```

### 4. Apply the Configuration

To deploy or update infrastructure:

```bash
terraform apply
```

Review the planned changes and type `yes` to confirm.

## State Backend Configuration

The Terraform state is stored remotely in AWS S3 with the following configuration:

- **Bucket**: `sudopay-terraform-state-staging`
- **State File**: `terraform.tfstate`
- **Region**: `us-east-1`
- **Encryption**: Enabled (AES256)
- **Locking**: DynamoDB table `sudopay-terraform-locks-staging`

### Why Remote State?

Remote state provides several benefits:
1. **Team Collaboration**: Multiple team members can work with the same state
2. **State Locking**: Prevents concurrent modifications that could corrupt state
3. **Security**: State is encrypted at rest and access can be controlled via IAM
4. **Versioning**: S3 versioning allows recovery from accidental changes
5. **Backup**: State is safely stored in AWS, not on local machines

## Working with Multiple Environments

The infrastructure is organized by environment (staging, production, etc.). Each environment has its own:
- State file in S3
- Backend configuration
- Variable values
- Resource naming conventions

To work with a different environment:

```bash
cd environments/<environment-name>
terraform init -backend-config=backend-config.hcl
```

## Security Best Practices

1. **Never commit state files**: State files are stored in S3, never in git
2. **Use IAM roles**: Configure AWS CLI with IAM roles rather than access keys when possible
3. **Encrypt sensitive variables**: Use AWS Secrets Manager or SSM Parameter Store for secrets
4. **Review plans carefully**: Always run `terraform plan` before `apply`
5. **Use workspaces carefully**: We use separate directories for environments for better isolation

## Troubleshooting

### Backend initialization fails

If `terraform init` fails with backend errors:

1. Verify the S3 bucket exists: `aws s3 ls | grep sudopay-terraform-state`
2. Verify the DynamoDB table exists: `aws dynamodb list-tables | grep sudopay-terraform-locks`
3. Check AWS credentials: `aws sts get-caller-identity`
4. Verify IAM permissions for S3 and DynamoDB access

### State locking errors

If you encounter state locking errors:

1. Check if another terraform process is running
2. Verify DynamoDB table is accessible
3. If stuck, you can force unlock (use with caution):
   ```bash
   terraform force-unlock <lock-id>
   ```

### State corruption

If state becomes corrupted:

1. S3 versioning is enabled - you can restore previous versions
2. List versions: `aws s3api list-object-versions --bucket sudopay-terraform-state-staging`
3. Restore specific version using AWS console or CLI

## Next Steps

After bootstrapping the state backend, proceed with:

1. **Shared Infrastructure**: VPC, networking, security groups
2. **Databases**: RDS PostgreSQL instances for each service
3. **Message Queues**: SQS queues for event processing
4. **Container Infrastructure**: ECS clusters, task definitions, services
5. **CI/CD**: GitHub Actions integration for automated deployments

## References

- [Terraform S3 Backend Documentation](https://www.terraform.io/docs/language/settings/backends/s3.html)
- [AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Terraform Best Practices](https://www.terraform-best-practices.com/)
