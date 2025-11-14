# Terraform Backend Configuration for Staging Networking
#
# This file configures the S3 backend for Terraform state storage.
# State files are stored in S3 with versioning enabled and encrypted at rest.
# DynamoDB is used for state locking to prevent concurrent modifications.
#
# Usage:
#   terraform init -backend-config=backend-config.hcl

bucket         = "sudopay-terraform-state-staging"
key            = "networking/terraform.tfstate"
region         = "us-east-1"
encrypt        = true
dynamodb_table = "sudopay-terraform-locks-staging"
