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
  backend "s3" {}
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
