# Outputs for Networking Module
# These outputs are used by other modules (ECS, RDS, etc.)

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = aws_subnet.public[*].id
}

output "private_app_subnet_ids" {
  description = "IDs of private application tier subnets"
  value       = aws_subnet.private_app[*].id
}

output "private_data_subnet_ids" {
  description = "IDs of private data tier subnets"
  value       = aws_subnet.private_data[*].id
}

output "availability_zones" {
  description = "List of availability zones used"
  value       = var.availability_zones
}

# Security Group IDs
output "alb_security_group_id" {
  description = "ID of the ALB security group"
  value       = aws_security_group.alb_public.id
}

output "nlb_security_group_id" {
  description = "ID of the NLB security group"
  value       = aws_security_group.nlb_internal.id
}

output "ecs_security_group_id" {
  description = "ID of the ECS services security group"
  value       = aws_security_group.ecs_services.id
}

output "rds_security_group_id" {
  description = "ID of the RDS security group"
  value       = aws_security_group.rds.id
}

output "vpc_endpoint_security_group_id" {
  description = "ID of the VPC endpoints security group"
  value       = aws_security_group.vpc_endpoints.id
}

# NAT Gateway IPs (useful for whitelisting)
output "nat_gateway_ips" {
  description = "Elastic IPs of NAT Gateways"
  value       = aws_eip.nat[*].public_ip
}

# VPC Endpoint IDs
output "vpc_endpoint_ecr_dkr_id" {
  description = "ID of ECR Docker VPC endpoint"
  value       = aws_vpc_endpoint.ecr_dkr.id
}

output "vpc_endpoint_ecr_api_id" {
  description = "ID of ECR API VPC endpoint"
  value       = aws_vpc_endpoint.ecr_api.id
}

output "vpc_endpoint_secretsmanager_id" {
  description = "ID of Secrets Manager VPC endpoint"
  value       = aws_vpc_endpoint.secretsmanager.id
}

output "vpc_endpoint_logs_id" {
  description = "ID of CloudWatch Logs VPC endpoint"
  value       = aws_vpc_endpoint.logs.id
}

output "vpc_endpoint_s3_id" {
  description = "ID of S3 Gateway VPC endpoint"
  value       = aws_vpc_endpoint.s3.id
}

output "vpc_endpoint_sqs_id" {
  description = "ID of SQS VPC endpoint"
  value       = aws_vpc_endpoint.sqs.id
}
