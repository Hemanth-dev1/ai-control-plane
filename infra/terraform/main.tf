# =============================================================================
# Terraform Configuration — Enterprise AI Control Plane (AWS)
# =============================================================================
# This Terraform configuration deploys the AI Control Plane to AWS with:
# - VPC with public/private subnets across 2 AZs
# - EKS cluster for container orchestration
# - RDS Postgres for persistence
# - MSK (Managed Kafka) for event streaming
# - Secrets Manager for secrets
# =============================================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
  }
  backend "s3" {
    # Configure with your bucket name:
    # bucket = "your-terraform-state-bucket"
    # key    = "ai-control-plane/terraform.tfstate"
    # region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region
}

# =============================================================================
# Data Sources
# =============================================================================
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

# =============================================================================
# VPC Module
# =============================================================================
module "vpc" {
  source = "./modules/vpc"

  vpc_name             = var.vpc_name
  vpc_cidr             = var.vpc_cidr
  availability_zones   = slice(data.aws_availability_zones.available.names, 0, 2)
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
}

# =============================================================================
# Secrets Manager
# =============================================================================
module "secrets_manager" {
  source = "./modules/secrets-manager"

  jwt_signing_key       = var.jwt_signing_key
  db_master_password    = var.db_master_password
  anthropic_api_key     = var.anthropic_api_key
}

# =============================================================================
# RDS Postgres
# =============================================================================
module "rds" {
  source = "./modules/rds"

  db_name              = var.db_name
  db_username          = var.db_username
  db_password          = module.secrets_manager.db_password_secret_arn
  db_instance_class    = var.db_instance_class
  vpc_id               = module.vpc.vpc_id
  private_subnet_ids   = module.vpc.private_subnet_ids
  allowed_security_group_ids = [module.eks.cluster_security_group_id]
}

# =============================================================================
# MSK (Managed Kafka)
# =============================================================================
module "msk" {
  source = "./modules/msk"

  cluster_name         = var.msk_cluster_name
  kafka_version        = var.kafka_version
  broker_instance_type = var.broker_instance_type
  broker_count         = var.broker_count
  vpc_id               = module.vpc.vpc_id
  private_subnet_ids   = module.vpc.private_subnet_ids
}

# =============================================================================
# EKS Cluster
# =============================================================================
module "eks" {
  source = "./modules/eks"

  cluster_name       = var.cluster_name
  cluster_version    = var.cluster_version
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  node_instance_type = var.node_instance_type
  node_group_size    = var.node_group_size
}

# =============================================================================
# Outputs
# =============================================================================
output "vpc_id" {
  value = module.vpc.vpc_id
}

output "eks_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "msk_bootstrap_brokers" {
  value = module.msk.bootstrap_brokers
}

output "secrets_manager_arns" {
  value = module.secrets_manager.secret_arns
}
