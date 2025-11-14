# Outputs for Staging Networking
# These outputs are passed through from the networking module

output "vpc_id" {
  description = "ID of the VPC"
  value       = module.networking.vpc_id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = module.networking.vpc_cidr
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = module.networking.public_subnet_ids
}

output "private_app_subnet_ids" {
  description = "IDs of private application tier subnets"
  value       = module.networking.private_app_subnet_ids
}

output "private_data_subnet_ids" {
  description = "IDs of private data tier subnets"
  value       = module.networking.private_data_subnet_ids
}

output "availability_zones" {
  description = "List of availability zones used"
  value       = module.networking.availability_zones
}

# Security Group IDs
output "alb_security_group_id" {
  description = "ID of the ALB security group"
  value       = module.networking.alb_security_group_id
}

output "nlb_security_group_id" {
  description = "ID of the NLB security group"
  value       = module.networking.nlb_security_group_id
}

output "ecs_security_group_id" {
  description = "ID of the ECS services security group"
  value       = module.networking.ecs_security_group_id
}

output "rds_security_group_id" {
  description = "ID of the RDS security group"
  value       = module.networking.rds_security_group_id
}

output "vpc_endpoint_security_group_id" {
  description = "ID of the VPC endpoints security group"
  value       = module.networking.vpc_endpoint_security_group_id
}

# NAT Gateway IPs
output "nat_gateway_ips" {
  description = "Elastic IPs of NAT Gateways"
  value       = module.networking.nat_gateway_ips
}

# VPC Endpoint IDs
output "vpc_endpoint_ecr_dkr_id" {
  description = "ID of ECR Docker VPC endpoint"
  value       = module.networking.vpc_endpoint_ecr_dkr_id
}

output "vpc_endpoint_ecr_api_id" {
  description = "ID of ECR API VPC endpoint"
  value       = module.networking.vpc_endpoint_ecr_api_id
}

output "vpc_endpoint_secretsmanager_id" {
  description = "ID of Secrets Manager VPC endpoint"
  value       = module.networking.vpc_endpoint_secretsmanager_id
}

output "vpc_endpoint_logs_id" {
  description = "ID of CloudWatch Logs VPC endpoint"
  value       = module.networking.vpc_endpoint_logs_id
}

output "vpc_endpoint_s3_id" {
  description = "ID of S3 Gateway VPC endpoint"
  value       = module.networking.vpc_endpoint_s3_id
}

output "vpc_endpoint_sqs_id" {
  description = "ID of SQS VPC endpoint"
  value       = module.networking.vpc_endpoint_sqs_id
}
