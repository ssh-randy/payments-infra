# Main Terraform configuration for Staging Environment

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend configuration is provided via backend-config.hcl
  # Run: terraform init -backend-config=backend-config.hcl
  # For local development, comment out the S3 backend to use local state
  # backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = "SudoPay"
      ManagedBy   = "Terraform"
    }
  }
}

# Data source to verify AWS connectivity
data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

# Output current AWS account and region information
output "aws_account_id" {
  description = "AWS Account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS Region"
  value       = data.aws_region.current.name
}

output "environment" {
  description = "Environment name"
  value       = var.environment
}

# ECR Repositories for container images
module "ecr" {
  source = "../../modules/ecr"

  environment            = var.environment
  service_names          = ["payment-token", "authorization-api", "auth-processor-worker"]
  image_retention_count  = 10
}

# Output ECR repository URLs for reference
output "ecr_repository_urls" {
  description = "ECR repository URLs for all services"
  value       = module.ecr.repository_urls
}
