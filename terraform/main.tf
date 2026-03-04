module "vpc" {
  source = "./modules/vpc"

  aws_region = var.aws_region
  vpc_cidr   = var.vpc_cidr
  tags       = var.tags
}

module "eks_cluster" {
  source = "./modules/eks-cluster"

  cluster_name       = var.cluster_name
  kubernetes_version = var.kubernetes_version
  subnet_ids         = module.vpc.private_subnet_ids
  vpc_id             = module.vpc.vpc_id
  tags               = var.tags
}

module "node_group" {
  source = "./modules/node-group"

  cluster_name       = module.eks_cluster.cluster_name
  cluster_version    = var.kubernetes_version
  node_instance_type = var.node_instance_type
  node_min_count     = var.node_min_count
  node_max_count     = var.node_max_count
  node_desired_count = var.node_desired_count
  subnet_ids         = module.vpc.private_subnet_ids
  tags               = var.tags
}

