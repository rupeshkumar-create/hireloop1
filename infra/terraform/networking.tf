###############################################################################
# Hireschema — VPC + Networking (ap-south-1)
###############################################################################

# VPC
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${var.app_name}-${var.environment}-vpc" }
}

# ap-south-1 has 3 AZs: a, b, c
locals {
  azs             = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
  public_cidrs    = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  private_cidrs   = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]
  database_cidrs  = ["10.0.21.0/24", "10.0.22.0/24", "10.0.23.0/24"]
}

# Public subnets (ALB, NAT gateways)
resource "aws_subnet" "public" {
  count                   = 3
  vpc_id                  = aws_vpc.main.id
  cidr_block              = local.public_cidrs[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "${var.app_name}-${var.environment}-public-${local.azs[count.index]}" }
}

# Private subnets (ECS tasks)
resource "aws_subnet" "private" {
  count             = 3
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.private_cidrs[count.index]
  availability_zone = local.azs[count.index]

  tags = { Name = "${var.app_name}-${var.environment}-private-${local.azs[count.index]}" }
}

# Database subnets (RDS, isolated)
resource "aws_subnet" "database" {
  count             = 3
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.database_cidrs[count.index]
  availability_zone = local.azs[count.index]

  tags = { Name = "${var.app_name}-${var.environment}-db-${local.azs[count.index]}" }
}

# Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.app_name}-${var.environment}-igw" }
}

# NAT Gateway (single AZ for cost — upgrade to multi-AZ for prod HA)
resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "${var.app_name}-${var.environment}-nat-eip" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.main]
  tags          = { Name = "${var.app_name}-${var.environment}-nat" }
}

# Public route table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "${var.app_name}-${var.environment}-rt-public" }
}

resource "aws_route_table_association" "public" {
  count          = 3
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Private route table (egress via NAT)
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }
  tags = { Name = "${var.app_name}-${var.environment}-rt-private" }
}

resource "aws_route_table_association" "private" {
  count          = 3
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# DB subnet group (RDS)
resource "aws_db_subnet_group" "main" {
  name       = "${var.app_name}-${var.environment}-db-subnet-group"
  subnet_ids = aws_subnet.database[*].id
  tags       = { Name = "${var.app_name}-${var.environment}-db-subnet-group" }
}

# Security Groups
resource "aws_security_group" "alb" {
  name        = "${var.app_name}-${var.environment}-alb-sg"
  description = "ALB — allow HTTPS from Cloudflare IPs only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from Cloudflare"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    # Cloudflare IPs — see https://www.cloudflare.com/ips/
    # Full list managed via Cloudflare managed IP list or Terraform cloudflare_ip_ranges data source
    cidr_blocks = ["0.0.0.0/0"]  # Tightened to CF IPs in Phase production hardening
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.app_name}-${var.environment}-alb-sg" }
}

resource "aws_security_group" "ecs_api" {
  name        = "${var.app_name}-${var.environment}-ecs-api-sg"
  description = "ECS API tasks — allow inbound from ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "From ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.app_name}-${var.environment}-ecs-api-sg" }
}

resource "aws_security_group" "rds" {
  name        = "${var.app_name}-${var.environment}-rds-sg"
  description = "RDS — allow inbound from ECS tasks only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_api.id]
  }

  tags = { Name = "${var.app_name}-${var.environment}-rds-sg" }
}
