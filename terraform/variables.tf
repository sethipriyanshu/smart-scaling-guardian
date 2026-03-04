variable "aws_region" {
  description = "AWS region for all provisioned resources"
  type        = string
  default     = "us-east-2"
}

variable "cluster_name" {
  description = "Name prefix for the EKS cluster"
  type        = string
  default     = "smart-scaling-guardian"
}

variable "kubernetes_version" {
  description = "Kubernetes version for the managed cluster"
  type        = string
  default     = "1.29"
}

variable "vpc_cidr" {
  description = "CIDR block for the provisioned VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "node_instance_type" {
  description = "EC2 instance type for worker nodes (use t3.micro for Free Tier–eligible accounts)"
  type        = string
  default     = "t3.micro"
}

variable "node_min_count" {
  description = "Minimum number of worker nodes in the node group"
  type        = number
  default     = 2
}

variable "node_max_count" {
  description = "Maximum number of worker nodes in the node group"
  type        = number
  default     = 10
}

variable "node_desired_count" {
  description = "Initial desired number of worker nodes"
  type        = number
  default     = 2
}

variable "tags" {
  description = "Map of tags applied to all AWS resources"
  type        = map(string)
  default = {
    project     = "smart-scaling-guardian"
    managed-by  = "terraform"
    environment = "dev"
  }
}

variable "environment" {
  description = "Deployment environment label (dev / staging / prod)"
  type        = string
  default     = "dev"
}

