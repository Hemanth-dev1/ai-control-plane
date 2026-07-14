# =============================================================================
# Variables — Enterprise AI Control Plane (AWS)
# =============================================================================

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "vpc_name" {
  description = "Name of the VPC"
  type        = string
  default     = "ai-control-plane-vpc"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "ai-control-plane-eks"
}

variable "cluster_version" {
  description = "Kubernetes version for EKS"
  type        = string
  default     = "1.29"
}

variable "node_instance_type" {
  description = "EC2 instance type for EKS worker nodes"
  type        = string
  default     = "t3.medium"
}

variable "node_group_size" {
  description = "Min/max/desired node count for the EKS node group"
  type = object({
    min     = number
    max     = number
    desired = number
  })
  default = {
    min     = 2
    max     = 6
    desired = 2
  }
}

variable "db_name" {
  description = "Name of the Postgres database"
  type        = string
  default     = "controlplane"
}

variable "db_username" {
  description = "Master username for RDS Postgres"
  type        = string
  default     = "controlplane"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_master_password" {
  description = "Master password for RDS (use Secrets Manager in production)"
  type        = string
  sensitive   = true
}

variable "msk_cluster_name" {
  description = "Name of the MSK cluster"
  type        = string
  default     = "ai-control-plane-msk"
}

variable "kafka_version" {
  description = "Kafka version for MSK"
  type        = string
  default     = "3.6.0"
}

variable "broker_instance_type" {
  description = "MSK broker instance type"
  type        = string
  default     = "kafka.t3.small"
}

variable "broker_count" {
  description = "Number of MSK brokers"
  type        = number
  default     = 2
}

variable "jwt_signing_key" {
  description = "JWT signing key (use Secrets Manager in production)"
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key for LLM access"
  type        = string
  sensitive   = true
}
