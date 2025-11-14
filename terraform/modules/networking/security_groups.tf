# Security Group - Public ALB
# Accepts HTTPS traffic from the internet, forwards to ECS services
resource "aws_security_group" "alb_public" {
  name_prefix = "${var.project_name}-${var.environment}-alb-public-"
  description = "Security group for public-facing Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-${var.environment}-alb-public"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "alb_public_https" {
  security_group_id = aws_security_group.alb_public.id
  description       = "Allow HTTPS from internet"

  cidr_ipv4   = "0.0.0.0/0"
  from_port   = 443
  to_port     = 443
  ip_protocol = "tcp"

  tags = {
    Name = "allow-https-from-internet"
  }
}

resource "aws_vpc_security_group_egress_rule" "alb_public_to_ecs" {
  security_group_id = aws_security_group.alb_public.id
  description       = "Allow traffic to ECS services on port 8000"

  referenced_security_group_id = aws_security_group.ecs_services.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"

  tags = {
    Name = "allow-to-ecs-services"
  }
}

# Security Group - Internal NLB
# For internal Payment Token Service communication
resource "aws_security_group" "nlb_internal" {
  name_prefix = "${var.project_name}-${var.environment}-nlb-internal-"
  description = "Security group for internal Network Load Balancer (Payment Token Service)"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-${var.environment}-nlb-internal"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "nlb_internal_from_ecs" {
  security_group_id = aws_security_group.nlb_internal.id
  description       = "Allow traffic from ECS services on port 8001"

  referenced_security_group_id = aws_security_group.ecs_services.id
  from_port                    = 8001
  to_port                      = 8001
  ip_protocol                  = "tcp"

  tags = {
    Name = "allow-from-ecs-services"
  }
}

resource "aws_vpc_security_group_egress_rule" "nlb_internal_to_ecs" {
  security_group_id = aws_security_group.nlb_internal.id
  description       = "Allow traffic to ECS services on port 8001"

  referenced_security_group_id = aws_security_group.ecs_services.id
  from_port                    = 8001
  to_port                      = 8001
  ip_protocol                  = "tcp"

  tags = {
    Name = "allow-to-ecs-services"
  }
}

# Security Group - ECS Services
# For all ECS tasks (Payment Token, Auth API, Auth Worker)
resource "aws_security_group" "ecs_services" {
  name_prefix = "${var.project_name}-${var.environment}-ecs-services-"
  description = "Security group for all ECS services"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-${var.environment}-ecs-services"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ECS Ingress - From ALB on port 8000
resource "aws_vpc_security_group_ingress_rule" "ecs_from_alb" {
  security_group_id = aws_security_group.ecs_services.id
  description       = "Allow traffic from ALB on port 8000"

  referenced_security_group_id = aws_security_group.alb_public.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"

  tags = {
    Name = "allow-from-alb-8000"
  }
}

# ECS Ingress - From NLB on port 8001
resource "aws_vpc_security_group_ingress_rule" "ecs_from_nlb" {
  security_group_id = aws_security_group.ecs_services.id
  description       = "Allow traffic from NLB on port 8001"

  referenced_security_group_id = aws_security_group.nlb_internal.id
  from_port                    = 8001
  to_port                      = 8001
  ip_protocol                  = "tcp"

  tags = {
    Name = "allow-from-nlb-8001"
  }
}

# ECS Ingress - Inter-service communication on port 8000
resource "aws_vpc_security_group_ingress_rule" "ecs_inter_service" {
  security_group_id = aws_security_group.ecs_services.id
  description       = "Allow inter-service communication on port 8000"

  referenced_security_group_id = aws_security_group.ecs_services.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"

  tags = {
    Name = "allow-inter-service-8000"
  }
}

# ECS Egress - To Internet for AWS APIs (HTTPS)
resource "aws_vpc_security_group_egress_rule" "ecs_to_internet" {
  security_group_id = aws_security_group.ecs_services.id
  description       = "Allow HTTPS to internet for AWS APIs"

  cidr_ipv4   = "0.0.0.0/0"
  from_port   = 443
  to_port     = 443
  ip_protocol = "tcp"

  tags = {
    Name = "allow-https-to-internet"
  }
}

# ECS Egress - To RDS on port 5432
resource "aws_vpc_security_group_egress_rule" "ecs_to_rds" {
  security_group_id = aws_security_group.ecs_services.id
  description       = "Allow traffic to RDS on port 5432"

  referenced_security_group_id = aws_security_group.rds.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"

  tags = {
    Name = "allow-to-rds-5432"
  }
}

# Security Group - RDS
# For PostgreSQL database instances
resource "aws_security_group" "rds" {
  name_prefix = "${var.project_name}-${var.environment}-rds-"
  description = "Security group for RDS PostgreSQL instances"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-${var.environment}-rds"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_ecs" {
  security_group_id = aws_security_group.rds.id
  description       = "Allow PostgreSQL from ECS services"

  referenced_security_group_id = aws_security_group.ecs_services.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"

  tags = {
    Name = "allow-from-ecs-5432"
  }
}

# No egress rules for RDS - it doesn't need to initiate outbound connections

# Security Group - VPC Endpoints
# For private connectivity to AWS services
resource "aws_security_group" "vpc_endpoints" {
  name_prefix = "${var.project_name}-${var.environment}-vpc-endpoints-"
  description = "Security group for VPC endpoints"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-${var.environment}-vpc-endpoints"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "vpc_endpoints_from_ecs" {
  security_group_id = aws_security_group.vpc_endpoints.id
  description       = "Allow HTTPS from ECS services"

  referenced_security_group_id = aws_security_group.ecs_services.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"

  tags = {
    Name = "allow-from-ecs-443"
  }
}

# No egress rules needed for VPC endpoints
