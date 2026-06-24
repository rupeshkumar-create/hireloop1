###############################################################################
# Hireloop — Root variable definitions
###############################################################################

variable "aws_region" {
  description = "AWS region — MUST be ap-south-1 (India geo-lock requirement)"
  type        = string
  default     = "ap-south-1"

  validation {
    condition     = var.aws_region == "ap-south-1"
    error_message = "Hireloop must deploy to ap-south-1 (Mumbai) per India geo-lock requirement."
  }
}

variable "environment" {
  description = "Deployment environment"
  type        = string

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Environment must be 'staging' or 'production'."
  }
}

variable "app_name" {
  description = "Application name used in resource naming"
  type        = string
  default     = "hireloop"
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with Zone:Edit and WAF:Edit permissions"
  type        = string
  sensitive   = true
}

variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for hireloop.in"
  type        = string
}

variable "cloudflare_account_id" {
  description = "Cloudflare Account ID"
  type        = string
}

variable "supabase_project_ref" {
  description = "Supabase project reference ID"
  type        = string
}

# VPC CIDR
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

# ECS
variable "api_cpu" {
  description = "ECS task CPU units for the API (1024 = 1 vCPU)"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "ECS task memory (MB) for the API"
  type        = number
  default     = 1024
}

variable "api_desired_count" {
  description = "Desired number of API task instances"
  type        = number
  default     = 1
}

# RDS (for LangGraph state + read replica)
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.micro"
}
