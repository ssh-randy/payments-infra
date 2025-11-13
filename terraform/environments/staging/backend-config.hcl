# Terraform Backend Configuration for Staging Environment
#
# This file configures the S3 backend for Terraform state storage.
# State files are stored in S3 with versioning enabled and encrypted at rest.
# DynamoDB is used for state locking to prevent concurrent modifications.
#
# Usage:
#   terraform init -backend-config=backend-config.hcl

bucket         = "sudopay-terraform-state-staging"
key            = "terraform.tfstate"
region         = "us-east-1"
encrypt        = true
dynamodb_table = "sudopay-terraform-locks-staging"

# Enable server-side encryption with AES256
# The S3 bucket has encryption enabled by default, but this ensures it's used
kms_key_id = null  # Use default AES256 encryption, not KMS

# Tags to apply to the state storage
# Note: These are applied at the infrastructure level, not via this config
