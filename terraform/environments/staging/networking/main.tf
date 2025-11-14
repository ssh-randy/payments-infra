# Staging Environment - Networking Configuration
# This configuration creates the VPC, subnets, security groups, and VPC endpoints for staging

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
      Project     = var.project_name
      ManagedBy   = "Terraform"
      Component   = "networking"
    }
  }
}

# Call the networking module
module "networking" {
  source = "../../../modules/networking"

  environment        = var.environment
  project_name       = var.project_name
  vpc_cidr           = var.vpc_cidr
  aws_region         = var.aws_region
  availability_zones = var.availability_zones

  # Staging uses single NAT Gateway for cost savings
  enable_nat_gateway = var.enable_nat_gateway
  single_nat_gateway = var.single_nat_gateway
}
