# ECR Module

This Terraform module creates AWS Elastic Container Registry (ECR) repositories for the payment infrastructure services.

## Features

- Creates ECR repositories for all payment services
- Enables automatic image scanning on push for security vulnerabilities
- Configures encryption at rest (AES-256)
- Implements lifecycle policies to retain only the last N images (default: 10)
- Supports MUTABLE image tags for flexible deployments

## Usage

```hcl
module "ecr" {
  source = "../../modules/ecr"

  environment            = "staging"
  service_names          = ["payment-token", "authorization-api", "auth-processor-worker"]
  image_retention_count  = 10
}
```

## Variables

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| environment | Environment name (e.g., staging, production) | string | - | yes |
| service_names | List of service names for ECR repositories | list(string) | - | yes |
| image_retention_count | Number of images to retain in ECR | number | 10 | no |
| tags | Additional tags to apply to resources | map(string) | {} | no |

## Outputs

| Name | Description |
|------|-------------|
| repository_urls | Map of service names to their ECR repository URLs |
| repository_arns | Map of service names to their ECR repository ARNs |
| repository_names | Map of service names to their ECR repository names |

## Repository Naming

Repositories are named using the pattern: `payments-{environment}/{service-name}`

For example:
- `payments-staging/payment-token`
- `payments-staging/authorization-api`
- `payments-staging/auth-processor-worker`

## Security Features

1. **Image Scanning**: Automatically scans images on push for vulnerabilities
2. **Encryption**: All images are encrypted at rest using AES-256
3. **Lifecycle Policies**: Automatically removes old images to reduce storage costs

## Lifecycle Policy

The module implements a lifecycle policy that:
- Keeps the last N images (configurable, default 10)
- Applies to all tags (tagged and untagged images)
- Automatically expires older images

This helps control storage costs while maintaining recent image history.
