terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# The Kubernetes provider will be configured after the EKS cluster is created.
# It is declared here so other modules can depend on it later.
provider "kubernetes" {
  host                   = "" # populated via data sources or explicit kubeconfig in a later iteration
  cluster_ca_certificate = ""
  token                  = ""
}

