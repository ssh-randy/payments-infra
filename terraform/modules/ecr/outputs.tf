# ECR Module Outputs

output "repository_urls" {
  description = "Map of service names to their ECR repository URLs"
  value = {
    for k, v in aws_ecr_repository.service :
    k => v.repository_url
  }
}

output "repository_arns" {
  description = "Map of service names to their ECR repository ARNs"
  value = {
    for k, v in aws_ecr_repository.service :
    k => v.arn
  }
}

output "repository_names" {
  description = "Map of service names to their ECR repository names"
  value = {
    for k, v in aws_ecr_repository.service :
    k => v.name
  }
}
